from __future__ import annotations

from decimal import Decimal

import pytest
import deal

from config.feature_flags import FeatureFlags
from synapse.shopify.shopify_writer import (
    ShopifyProductInput,
    ShopifyVariantInput,
    ShopifyWriter,
)


def test_create_product_mock_mode():
    flags = FeatureFlags(shopify_live=False)
    w = ShopifyWriter(shop="test-shop", access_token="x", flags=flags)
    prod = ShopifyProductInput(
        title="Test Product",
        body_html="<p>hi</p>",
        vendor="Trendify",
        product_type="Gadgets",
        tags=["a", "b"],
        variants=[
            ShopifyVariantInput(
                sku="SKU1",
                price=Decimal("199.99"),
                compare_at_price=None,
                inventory_quantity=10,
            )
        ],
    )
    r = w.create_product(prod)
    assert r.success is True
    assert r.mock is True
    assert isinstance(r.product_id, str)
    assert r.product_id.startswith("gid://shopify/Product/")


def test_create_product_requires_title():
    flags = FeatureFlags(shopify_live=False)
    w = ShopifyWriter(shop="test-shop", access_token="x", flags=flags)
    prod = ShopifyProductInput(
        title="",
        body_html="",
        vendor="Trendify",
        product_type="Gadgets",
        tags=[],
        variants=[
            ShopifyVariantInput(
                sku="SKU1",
                price=Decimal("10"),
                compare_at_price=None,
                inventory_quantity=1,
            )
        ],
    )
    with pytest.raises(deal.PreContractError):
        w.create_product(prod)


def test_create_product_requires_variant():
    flags = FeatureFlags(shopify_live=False)
    w = ShopifyWriter(shop="test-shop", access_token="x", flags=flags)
    prod = ShopifyProductInput(
        title="X",
        body_html="",
        vendor="Trendify",
        product_type="Gadgets",
        tags=[],
        variants=[],
    )
    with pytest.raises(deal.PreContractError):
        w.create_product(prod)


def test_set_product_status_draft_to_active():
    flags = FeatureFlags(shopify_live=False)
    w = ShopifyWriter(shop="test-shop", access_token="x", flags=flags)
    r = w.set_product_status("gid://shopify/Product/MOCK-1", "ACTIVE")
    assert r.success is True
    assert r.mock is True
    assert r.product_id == "gid://shopify/Product/MOCK-1"
    assert r.errors == []
