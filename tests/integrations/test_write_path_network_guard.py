from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from config.feature_flags import FeatureFlags
import synapse.shopify.shopify_writer as shopify_writer
from synapse.meta.publisher_adapter import call_create_campaign
from synapse.meta.publisher_contracts import MetaCampaignPayload


def _shopify_product() -> shopify_writer.ShopifyProductInput:
    return shopify_writer.ShopifyProductInput(
        title="Guarded Product",
        body_html="guarded",
        vendor="Trendify",
        product_type="General",
        tags=["guard"],
        variants=[
            shopify_writer.ShopifyVariantInput(
                sku="GUARD-SKU-001",
                price=Decimal("19.99"),
                compare_at_price=None,
                inventory_quantity=1,
                requires_shipping=True,
            )
        ],
        status="DRAFT",
    )


def test_shopify_writer_blocks_at_network_guard_before_post_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SYNAPSE_SHOPIFY_LIVE", "1")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")

    calls: list[dict[str, object]] = []

    def post_json_should_not_run(self, url, payload, headers, timeout_s):  # noqa: ANN001
        calls.append({"url": url, "payload": payload, "headers": headers, "timeout_s": timeout_s})
        raise AssertionError("post_json must not run before network_guard")

    monkeypatch.setattr(shopify_writer.SimpleHttpClient, "post_json", post_json_should_not_run, raising=True)

    writer = shopify_writer.ShopifyWriter(
        shop="guard-shop",
        access_token="shpat_guard",
        flags=FeatureFlags(
            shopify_live=True,
            meta_live=False,
            dropi_live=False,
            spend_real_money=False,
        ),
        config=shopify_writer.ShopifyWriterConfig(
            api_version="2026-01",
            timeout_s=1.0,
            max_retries=0,
            idempotency_db_path=tmp_path / "shopify-writer-guard.sqlite3",
            idempotency_ttl_seconds=3600,
        ),
    )

    result = writer.create_product(_shopify_product())

    assert result.success is False
    assert result.mock is False
    assert calls == []
    assert any("NETWORK_BLOCKED_BY_FLAGS" in error for error in result.errors)


def test_meta_publisher_ignores_synapse_flag_live_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "1")
    monkeypatch.delenv("SYNAPSE_META_LIVE", raising=False)
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_guard")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    with pytest.raises(NotImplementedError, match="Live Meta campaign creation"):
        call_create_campaign(MetaCampaignPayload(name="Alias Must Not Enable Live"))


def test_meta_publisher_blocks_at_network_guard_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_META_LIVE", "1")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "1")
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_guard")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    calls: list[object] = []

    class _FakeClient:
        def request(self, req):  # noqa: ANN001
            calls.append(req)
            raise AssertionError("request must not run before network_guard")

    with patch("synapse.meta.publisher_adapter._build_http_client", return_value=_FakeClient()):
        with pytest.raises(RuntimeError, match="NETWORK_BLOCKED_BY_FLAGS"):
            call_create_campaign(MetaCampaignPayload(name="Guarded Meta Campaign"))

    assert calls == []


def test_featureflags_load_seals_synapse_flag_live_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "1")
    monkeypatch.setenv("SYNAPSE_FLAG_SHOPIFY_LIVE_API", "1")
    monkeypatch.setenv("SYNAPSE_FLAG_DROPI_LIVE_ORDERS", "1")
    monkeypatch.setenv("SYNAPSE_FLAG_SPEND_REAL_MONEY_API", "1")
    monkeypatch.delenv("SYNAPSE_META_LIVE", raising=False)
    monkeypatch.delenv("SYNAPSE_SHOPIFY_LIVE", raising=False)
    monkeypatch.delenv("SYNAPSE_DROPI_LIVE", raising=False)
    monkeypatch.delenv("SYNAPSE_SPEND_REAL_MONEY", raising=False)

    flags = FeatureFlags.load()

    assert flags.meta_live is False
    assert flags.shopify_live is False
    assert flags.dropi_live is False
    assert flags.spend_real_money is False
    assert flags.meta_live_api is False
    assert flags.shopify_live_api is False
    assert flags.dropi_live_orders is False
    assert flags.spend_real_money_api is False
    assert flags.is_on("meta_live_api", default=False) is False
