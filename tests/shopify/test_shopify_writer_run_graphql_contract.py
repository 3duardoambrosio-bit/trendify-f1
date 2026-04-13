from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch, call

import synapse.shopify.shopify_writer as m


def _writer(*, max_retries: int = 2) -> m.ShopifyWriter:
    return m.ShopifyWriter(
        shop="test-shop",
        access_token="shpat_fake_token",
        flags=m.FeatureFlags(
            shopify_live=True,
            meta_live=False,
            dropi_live=False,
            spend_real_money=False,
        ),
        config=m.ShopifyWriterConfig(
            api_version="2026-01",
            timeout_s=3.0,
            max_retries=max_retries,
        ),
    )


def _product() -> m.ShopifyProductInput:
    return m.ShopifyProductInput(
        title="Contract Product",
        body_html="<p>contract</p>",
        vendor="Trendify",
        product_type="General",
        tags=["contract"],
        variants=[
            m.ShopifyVariantInput(
                sku="SKU-CONTRACT-1",
                price=Decimal("19.99"),
                compare_at_price=None,
                inventory_quantity=5,
                requires_shipping=True,
            )
        ],
        status="DRAFT",
    )


def test_http_status_non_200_returns_exact_error_and_does_not_retry():
    writer = _writer(max_retries=2)

    with patch.object(writer, "_http_post", return_value=(503, "upstream_down")) as mock_post, patch(
        "synapse.shopify.shopify_writer.time.sleep"
    ) as mock_sleep:
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert result.product_id is None
    assert result.errors == ["http_status=503", "upstream_down"]
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_graphql_errors_are_stringified():
    writer = _writer(max_retries=1)
    payload = {
        "errors": [
            {"message": "bad query"},
            {"code": "X123"},
        ],
        "data": {"productCreate": None},
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))):
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert len(result.errors) == 2
    assert any("bad query" in e for e in result.errors)
    assert any("X123" in e for e in result.errors)


def test_user_errors_are_extracted():
    writer = _writer(max_retries=1)
    payload = {
        "data": {
            "productCreate": {
                "product": None,
                "userErrors": [
                    {"field": "title", "message": "required"},
                    {"message": "bad tag"},
                ],
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))):
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert result.errors == ["title: required", "bad tag"]


def test_user_errors_not_list_fails_closed():
    writer = _writer(max_retries=1)
    payload = {
        "data": {
            "productCreate": {
                "product": None,
                "userErrors": {"message": "wrong-shape"},
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))):
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert result.errors == ["userErrors_not_list"]


def test_create_product_missing_id_returns_specific_error():
    writer = _writer(max_retries=1)
    payload = {
        "data": {
            "productCreate": {
                "product": {},
                "userErrors": [],
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))):
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert result.product_id is None
    assert result.errors == ["productCreate_missing_id"]


def test_update_product_missing_response_id_falls_back_to_input_id():
    writer = _writer(max_retries=1)
    payload = {
        "data": {
            "productUpdate": {
                "product": {},
                "userErrors": [],
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))):
        result = writer.update_product(
            "gid://shopify/Product/123",
            {"title": "Updated"},
        )

    assert result.success is True
    assert result.mock is False
    assert result.product_id == "gid://shopify/Product/123"
    assert result.errors == []


def test_update_variant_price_success_returns_ok():
    writer = _writer(max_retries=1)
    payload = {
        "data": {
            "productVariantUpdate": {
                "productVariant": {"id": "gid://shopify/ProductVariant/456"},
                "userErrors": [],
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))):
        result = writer.update_variant_price(
            "gid://shopify/ProductVariant/456",
            Decimal("29.99"),
        )

    assert result.success is True
    assert result.mock is False
    assert result.product_id is None
    assert result.errors == []


def test_transport_exception_retries_with_incremental_backoff_and_returns_last_error():
    writer = _writer(max_retries=2)

    with patch.object(writer, "_http_post", side_effect=RuntimeError("transport blocked")) as mock_post, patch(
        "synapse.shopify.shopify_writer.time.sleep"
    ) as mock_sleep:
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert result.product_id is None
    assert len(result.errors) == 1
    assert "RuntimeError" in result.errors[0]
    assert "transport blocked" in result.errors[0]

    assert mock_post.call_count == 3
    assert mock_sleep.call_args_list == [call(0.25), call(0.5)]
