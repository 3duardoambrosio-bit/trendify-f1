from pathlib import Path

import pytest

from synapse.ui import read_model
from synapse.ui._shopify_fixture_schema import (
    ShopifyFixtureSchemaError,
    validate_shopify_ops_fixture,
    validate_shopify_products_fixture,
)


def product_fixture(**overrides):
    product = {
        "category": "gadgets",
        "cost": 219.0,
        "image_url": "https://example.test/neck-fan.jpg",
        "images_count": 4,
        "keyword_matches": ["neck fan", "portable fan"],
        "margin_absolute": 280.0,
        "margin_percent": 56.11,
        "match_score": 0.91,
        "price": 499.0,
        "product_id": "prod-alpha",
        "rating": 4.7,
        "reviews": 184,
        "sales": 920,
        "shipping_days": 7,
        "supplier_id": "supplier-alpha",
        "supplier_name": "Dropi Alpha",
        "title": "Neck Fan Pro",
    }
    product.update(overrides)
    return product


def ops_fixture(**overrides):
    ops = {
        "circuit_breaker": {},
        "dropi": {},
        "finance": {},
        "flags": {
            "dropi_live": False,
            "meta_live": False,
            "shopify_live": False,
            "spend_real_money": False,
        },
        "healthy": True,
        "meta": {},
        "shopify": {
            "api_ok": True,
            "checkout_ok": True,
            "orders_last_hour": 0,
        },
        "signals": {},
        "status": "nominal",
        "timestamp": "2026-05-28T00:00:00Z",
        "ts": "2026-05-28T00:00:00Z",
    }
    ops.update(overrides)
    return ops


def test_current_nominal_shopify_fixtures_satisfy_schema() -> None:
    snapshot = read_model.load_shopify_read_only_snapshot()

    assert snapshot.product_count == 2
    assert snapshot.shopify_live_enabled is False
    assert snapshot.spend_real_money_enabled is False


def test_products_schema_accepts_valid_rows() -> None:
    rows = validate_shopify_products_fixture([product_fixture()], Path("products.json"))

    assert rows[0]["product_id"] == "prod-alpha"
    assert rows[0]["keyword_matches"] == ["neck fan", "portable fan"]


def test_products_schema_rejects_missing_required_field() -> None:
    product = product_fixture()
    del product["price"]

    with pytest.raises(ShopifyFixtureSchemaError, match="missing field.*price"):
        validate_shopify_products_fixture([product], Path("products.json"))


def test_products_schema_rejects_wrong_field_type() -> None:
    product = product_fixture(price="499")

    with pytest.raises(ShopifyFixtureSchemaError, match=r"products\[0\]\.price expected number"):
        validate_shopify_products_fixture([product], Path("products.json"))


def test_products_schema_rejects_unexpected_secret_like_field() -> None:
    product = product_fixture(admin_secret="must_not_surface")

    with pytest.raises(ShopifyFixtureSchemaError, match="unexpected field.*admin_secret"):
        validate_shopify_products_fixture([product], Path("products.json"))


def test_products_schema_rejects_non_string_keyword_matches() -> None:
    product = product_fixture(keyword_matches=["ok", 123])

    with pytest.raises(ShopifyFixtureSchemaError, match=r"keyword_matches expected list\[str\]"):
        validate_shopify_products_fixture([product], Path("products.json"))


def test_ops_schema_accepts_empty_mapping_for_missing_optional_fixture() -> None:
    assert validate_shopify_ops_fixture({}, Path("ops.json")) == {}


def test_ops_schema_accepts_valid_read_only_tick() -> None:
    ops = validate_shopify_ops_fixture(ops_fixture(), Path("ops.json"))

    assert ops["flags"]["shopify_live"] is False
    assert ops["shopify"]["orders_last_hour"] == 0


def test_ops_schema_rejects_missing_flag_field() -> None:
    flags = {
        "dropi_live": False,
        "meta_live": False,
        "shopify_live": False,
    }
    ops = ops_fixture(flags=flags)

    with pytest.raises(ShopifyFixtureSchemaError, match=r"ops_tick\.flags missing field.*spend_real_money"):
        validate_shopify_ops_fixture(ops, Path("ops.json"))


def test_ops_schema_rejects_live_or_spend_flags() -> None:
    ops = ops_fixture(
        flags={
            "dropi_live": False,
            "meta_live": False,
            "shopify_live": True,
            "spend_real_money": False,
        }
    )

    with pytest.raises(ShopifyFixtureSchemaError, match="shopify_live must be False"):
        validate_shopify_ops_fixture(ops, Path("ops.json"))


def test_ops_schema_rejects_wrong_shopify_metric_type() -> None:
    ops = ops_fixture(
        shopify={
            "api_ok": True,
            "checkout_ok": True,
            "orders_last_hour": "0",
        }
    )

    with pytest.raises(ShopifyFixtureSchemaError, match="orders_last_hour expected int"):
        validate_shopify_ops_fixture(ops, Path("ops.json"))
