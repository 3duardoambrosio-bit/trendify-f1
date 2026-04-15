from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
import synapse.shopify.shopify_writer as m


def _writer(*, max_retries: int = 2, idempotency_db_path: Path | None = None) -> m.ShopifyWriter:
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
            idempotency_db_path=idempotency_db_path or Path("runtime/idempotency/test-shopify-writer.sqlite3"),
            idempotency_ttl_seconds=3600,
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


def test_http_status_non_200_returns_exact_error_and_does_not_retry(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")

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


def test_graphql_errors_are_stringified(tmp_path):
    writer = _writer(max_retries=1, idempotency_db_path=tmp_path / "idem.sqlite3")
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


def test_user_errors_are_extracted(tmp_path):
    writer = _writer(max_retries=1, idempotency_db_path=tmp_path / "idem.sqlite3")
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


def test_user_errors_not_list_fails_closed(tmp_path):
    writer = _writer(max_retries=1, idempotency_db_path=tmp_path / "idem.sqlite3")
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


def test_create_product_missing_id_returns_specific_error(tmp_path):
    writer = _writer(max_retries=1, idempotency_db_path=tmp_path / "idem.sqlite3")
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


def test_graphql_data_null_fails_closed_without_retry(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")
    payload = {"data": None}

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))) as mock_post, patch(
        "synapse.shopify.shopify_writer.time.sleep"
    ) as mock_sleep:
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert result.product_id is None
    assert result.errors == ["graphql_data_missing_or_invalid"]
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_graphql_top_level_null_fails_closed_without_retry(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")
    payload = {"data": {"productCreate": None}}

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))) as mock_post, patch(
        "synapse.shopify.shopify_writer.time.sleep"
    ) as mock_sleep:
        result = writer.create_product(_product())

    assert result.success is False
    assert result.mock is False
    assert result.product_id is None
    assert result.errors == ["graphql_top_level_null:productCreate"]
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_create_product_success_is_idempotent_across_duplicate_calls(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")
    payload = {
        "data": {
            "productCreate": {
                "product": {"id": "gid://shopify/Product/999"},
                "userErrors": [],
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))) as mock_post:
        first = writer.create_product(_product())
        second = writer.create_product(_product())

    assert first.success is True
    assert first.product_id == "gid://shopify/Product/999"
    assert first.errors == []
    assert second.success is True
    assert second.product_id == "gid://shopify/Product/999"
    assert second.errors == []
    assert mock_post.call_count == 1


def test_update_product_missing_response_id_falls_back_to_input_id(tmp_path):
    writer = _writer(max_retries=1, idempotency_db_path=tmp_path / "idem.sqlite3")
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


def test_update_product_success_is_idempotent_across_duplicate_calls(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")
    payload = {
        "data": {
            "productUpdate": {
                "product": {"id": "gid://shopify/Product/123"},
                "userErrors": [],
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))) as mock_post:
        first = writer.update_product("gid://shopify/Product/123", {"title": "Updated"})
        second = writer.update_product("gid://shopify/Product/123", {"title": "Updated"})

    assert first.success is True
    assert first.product_id == "gid://shopify/Product/123"
    assert second.success is True
    assert second.product_id == "gid://shopify/Product/123"
    assert mock_post.call_count == 1


def test_update_variant_price_success_returns_ok(tmp_path):
    writer = _writer(max_retries=1, idempotency_db_path=tmp_path / "idem.sqlite3")
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


def test_update_variant_price_success_is_idempotent_across_duplicate_calls(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")
    payload = {
        "data": {
            "productVariantUpdate": {
                "productVariant": {"id": "gid://shopify/ProductVariant/456"},
                "userErrors": [],
            }
        }
    }

    with patch.object(writer, "_http_post", return_value=(200, json.dumps(payload))) as mock_post:
        first = writer.update_variant_price("gid://shopify/ProductVariant/456", Decimal("29.99"))
        second = writer.update_variant_price("gid://shopify/ProductVariant/456", Decimal("29.99"))

    assert first.success is True
    assert second.success is True
    assert mock_post.call_count == 1


def test_transport_exception_does_not_retry_unsafe_create_product(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")

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
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_transport_exception_does_not_retry_unsafe_update_product(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")

    with patch.object(writer, "_http_post", side_effect=RuntimeError("transport blocked")) as mock_post, patch(
        "synapse.shopify.shopify_writer.time.sleep"
    ) as mock_sleep:
        result = writer.update_product("gid://shopify/Product/123", {"title": "Updated"})

    assert result.success is False
    assert result.mock is False
    assert result.product_id is None
    assert len(result.errors) == 1
    assert "RuntimeError" in result.errors[0]
    assert "transport blocked" in result.errors[0]
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_transport_exception_does_not_retry_unsafe_update_variant_price(tmp_path):
    writer = _writer(max_retries=2, idempotency_db_path=tmp_path / "idem.sqlite3")

    with patch.object(writer, "_http_post", side_effect=RuntimeError("transport blocked")) as mock_post, patch(
        "synapse.shopify.shopify_writer.time.sleep"
    ) as mock_sleep:
        result = writer.update_variant_price("gid://shopify/ProductVariant/456", Decimal("29.99"))

    assert result.success is False
    assert result.mock is False
    assert result.product_id is None
    assert len(result.errors) == 1
    assert "RuntimeError" in result.errors[0]
    assert "transport blocked" in result.errors[0]
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_update_single_variant_fields_is_explicitly_not_implemented():
    with pytest.raises(NotImplementedError, match="not implemented"):
        m._update_single_variant_fields(
            "gid://shopify/ProductVariant/456",
            m.ShopifyVariantInput(
                sku="SKU-1",
                price=Decimal("19.99"),
                compare_at_price=None,
                inventory_quantity=1,
                requires_shipping=True,
            ),
        )

def test_run_graphql_transport_exception_returns_stable_error_code(monkeypatch):
    writer = m.ShopifyWriter(
        shop="demo-shop",
        access_token="token",
        flags=m.FeatureFlags(shopify_live=True, meta_live=False, dropi_live=False, spend_real_money=False),
    )

    def boom(url, payload, headers, timeout_s):
        raise TimeoutError("socket timeout")

    monkeypatch.setattr(writer._http, "post_json", boom, raising=True)

    out = writer._run_graphql("mutation X { productCreate(input: {}) { product { id } userErrors { field message } } }", {})

    assert out["ok"] is False
    assert out["errors"] == ["graphql_transport_error:TimeoutError:socket timeout"]


def test_execute_idempotent_write_unexpected_exception_returns_stable_error_code(monkeypatch):
    writer = m.ShopifyWriter(
        shop="demo-shop",
        access_token="token",
        flags=m.FeatureFlags(shopify_live=True, meta_live=False, dropi_live=False, spend_real_money=False),
    )

    def fake_execute_once(**kwargs):
        raise RuntimeError("sqlite unavailable")

    monkeypatch.setattr(m, "execute_once", fake_execute_once, raising=True)

    out = writer._execute_idempotent_write(
        operation_name="create_product",
        idempotency_key="idem-123",
        mutation="mutation X { productCreate(input: {}) { product { id } userErrors { field message } } }",
        variables={},
        extractor=lambda out: {"product_id": "gid://shopify/Product/1"},
    )

    assert out["success"] is False
    assert out["product_id"] is None
    assert out["errors"] == ["idempotency_execution_error:RuntimeError"]
