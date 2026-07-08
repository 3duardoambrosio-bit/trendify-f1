"""Runtime schema contract for local Shopify-like UI fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn


class ShopifyFixtureSchemaError(ValueError):
    """Raised when a local Shopify fixture violates the expected schema."""


SHOPIFY_PRODUCT_REQUIRED_FIELDS = (
    "category",
    "cost",
    "image_url",
    "images_count",
    "keyword_matches",
    "margin_absolute",
    "margin_percent",
    "match_score",
    "price",
    "product_id",
    "rating",
    "reviews",
    "sales",
    "shipping_days",
    "supplier_id",
    "supplier_name",
    "title",
)

SHOPIFY_PRODUCT_FIELD_KINDS: Mapping[str, str] = {
    "category": "str",
    "cost": "number",
    "image_url": "str",
    "images_count": "int",
    "keyword_matches": "list[str]",
    "margin_absolute": "number",
    "margin_percent": "number",
    "match_score": "number",
    "price": "number",
    "product_id": "str",
    "rating": "number",
    "reviews": "int",
    "sales": "int",
    "shipping_days": "int",
    "supplier_id": "str",
    "supplier_name": "str",
    "title": "str",
}

SHOPIFY_OPS_TOP_LEVEL_FIELDS: Mapping[str, str] = {
    "circuit_breaker": "mapping",
    "dropi": "mapping",
    "finance": "mapping",
    "flags": "mapping",
    "healthy": "bool",
    "meta": "mapping",
    "shopify": "mapping",
    "signals": "mapping",
    "status": "str",
    "timestamp": "str",
    "ts": "str",
}

SHOPIFY_READ_ONLY_FLAG_FIELDS = (
    "dropi_live",
    "meta_live",
    "shopify_live",
    "spend_real_money",
)

SHOPIFY_HEALTH_FIELDS: Mapping[str, str] = {
    "api_ok": "bool",
    "checkout_ok": "bool",
    "orders_last_hour": "int",
}


def _fail(source: Path | str, message: str) -> NoReturn:
    raise ShopifyFixtureSchemaError(f"{source}: {message}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _kind_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if _is_int(value):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, Mapping):
        return "mapping"
    if value is None:
        return "null"
    return type(value).__name__


def _validate_kind(value: Any, expected_kind: str, source: Path | str, field_path: str) -> None:
    if expected_kind == "str" and isinstance(value, str):
        return
    if expected_kind == "bool" and isinstance(value, bool):
        return
    if expected_kind == "int" and _is_int(value):
        return
    if expected_kind == "number" and _is_number(value):
        return
    if expected_kind == "mapping" and isinstance(value, Mapping):
        return
    if expected_kind == "list[str]" and isinstance(value, list) and all(isinstance(item, str) for item in value):
        return

    _fail(source, f"{field_path} expected {expected_kind}, got {_kind_name(value)}")


def _validate_exact_keys(
    value: Mapping[str, Any],
    expected_keys: Sequence[str],
    source: Path | str,
    label: str,
) -> None:
    expected = set(expected_keys)
    actual = set(value)

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)

    if missing:
        _fail(source, f"{label} missing field(s): {', '.join(missing)}")
    if unexpected:
        _fail(source, f"{label} unexpected field(s): {', '.join(unexpected)}")


def validate_shopify_products_fixture(
    products: Any,
    source: Path | str,
) -> list[Mapping[str, Any]]:
    if not isinstance(products, Sequence) or isinstance(products, (str, bytes, bytearray)):
        _fail(source, f"products expected list, got {_kind_name(products)}")

    validated: list[Mapping[str, Any]] = []

    for index, product in enumerate(products):
        label = f"products[{index}]"

        if not isinstance(product, Mapping):
            _fail(source, f"{label} expected mapping, got {_kind_name(product)}")

        _validate_exact_keys(product, SHOPIFY_PRODUCT_REQUIRED_FIELDS, source, label)

        for field in SHOPIFY_PRODUCT_REQUIRED_FIELDS:
            _validate_kind(
                product[field],
                SHOPIFY_PRODUCT_FIELD_KINDS[field],
                source,
                f"{label}.{field}",
            )

        validated.append(dict(product))

    return validated


def validate_shopify_ops_fixture(
    ops_tick: Any,
    source: Path | str,
) -> Mapping[str, Any]:
    if not isinstance(ops_tick, Mapping):
        _fail(source, f"ops_tick expected mapping, got {_kind_name(ops_tick)}")

    if not ops_tick:
        return {}

    _validate_exact_keys(ops_tick, tuple(SHOPIFY_OPS_TOP_LEVEL_FIELDS), source, "ops_tick")

    for field, expected_kind in SHOPIFY_OPS_TOP_LEVEL_FIELDS.items():
        _validate_kind(ops_tick[field], expected_kind, source, f"ops_tick.{field}")

    flags = ops_tick["flags"]
    if not isinstance(flags, Mapping):
        _fail(source, f"ops_tick.flags expected mapping, got {_kind_name(flags)}")

    _validate_exact_keys(flags, SHOPIFY_READ_ONLY_FLAG_FIELDS, source, "ops_tick.flags")

    for field in SHOPIFY_READ_ONLY_FLAG_FIELDS:
        _validate_kind(flags[field], "bool", source, f"ops_tick.flags.{field}")
        if flags[field] is not False:
            _fail(source, f"ops_tick.flags.{field} must be False for local read-only fixtures")

    shopify = ops_tick["shopify"]
    if not isinstance(shopify, Mapping):
        _fail(source, f"ops_tick.shopify expected mapping, got {_kind_name(shopify)}")

    _validate_exact_keys(shopify, tuple(SHOPIFY_HEALTH_FIELDS), source, "ops_tick.shopify")

    for field, expected_kind in SHOPIFY_HEALTH_FIELDS.items():
        _validate_kind(shopify[field], expected_kind, source, f"ops_tick.shopify.{field}")

    return dict(ops_tick)
