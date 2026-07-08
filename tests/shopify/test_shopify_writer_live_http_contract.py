from decimal import Decimal
from pathlib import Path

import synapse.shopify.shopify_writer as m

WRONG_HTTP_METHOD = "WRONG_HTTP_METHOD_USED"
NETWORK_BLOCKED = "NETWORK_BLOCKED_BY_FLAGS"


def _build_writer(monkeypatch, tmp_path: Path):
    calls = []

    def wrong_method(*args, **kwargs):
        raise RuntimeError(WRONG_HTTP_METHOD)

    def blocked_post_json(self, url, payload, headers, timeout_s):
        calls.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers,
                "timeout_s": timeout_s,
            }
        )
        raise RuntimeError(NETWORK_BLOCKED)

    monkeypatch.setattr(m.SimpleHttpClient, "get", wrong_method, raising=True)
    monkeypatch.setattr(m.SimpleHttpClient, "request", wrong_method, raising=True)
    monkeypatch.setattr(m.SimpleHttpClient, "post_json", blocked_post_json, raising=True)

    writer = m.ShopifyWriter(
        shop="invalid-shop",
        access_token="shpat_fake_token",
        flags=m.FeatureFlags(
            shopify_live=True,
            meta_live=False,
            dropi_live=False,
            spend_real_money=False,
        ),
        config=m.ShopifyWriterConfig(
            api_version="2026-01",
            timeout_s=1.0,
            max_retries=2,
            idempotency_db_path=tmp_path / "shopify-writer-live-http.sqlite3",
            idempotency_ttl_seconds=3600,
        ),
    )
    return writer, calls


def _build_product():
    return m.ShopifyProductInput(
        title="Live Negative Smoke",
        body_html="smoke",
        vendor="Trendify",
        product_type="General",
        tags=["smoke", "live-negative"],
        variants=[
            m.ShopifyVariantInput(
                sku="NEG-SKU-001",
                price=Decimal("19.99"),
                compare_at_price=Decimal("19.99"),
                inventory_quantity=1,
                requires_shipping=True,
            )
        ],
        status="DRAFT",
    )


def _assert_network_blocked_result(result):
    assert result.success is False
    assert result.mock is False
    assert result.errors

    joined = " | ".join(result.errors)
    assert NETWORK_BLOCKED in joined
    assert WRONG_HTTP_METHOD not in joined
    assert "no attribute 'post'" not in joined


def _assert_network_guard_blocked_before_post_json(calls):
    assert calls == []


def test_live_create_product_uses_post_json(monkeypatch, tmp_path):
    writer, calls = _build_writer(monkeypatch, tmp_path)

    result = writer.create_product(_build_product())

    _assert_network_blocked_result(result)
    _assert_network_guard_blocked_before_post_json(calls)


def test_live_update_product_uses_post_json(monkeypatch, tmp_path):
    writer, calls = _build_writer(monkeypatch, tmp_path)

    result = writer.update_product(
        "gid://shopify/Product/123",
        {"title": "Live Updated"},
    )

    _assert_network_blocked_result(result)
    _assert_network_guard_blocked_before_post_json(calls)
    assert result.product_id is None


def test_live_set_product_status_uses_post_json(monkeypatch, tmp_path):
    writer, calls = _build_writer(monkeypatch, tmp_path)

    result = writer.set_product_status(
        "gid://shopify/Product/123",
        "DRAFT",
    )

    _assert_network_blocked_result(result)
    _assert_network_guard_blocked_before_post_json(calls)
    assert result.product_id is None


def test_live_update_variant_price_uses_post_json(monkeypatch, tmp_path):
    writer, calls = _build_writer(monkeypatch, tmp_path)

    result = writer.update_variant_price(
        "gid://shopify/ProductVariant/456",
        Decimal("19.99"),
    )

    _assert_network_blocked_result(result)
    _assert_network_guard_blocked_before_post_json(calls)