from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class DropiFixtureValidationError(ValueError):
    """Raised when a Dropi fixture violates the read-only contract."""


ALLOWED_STOCK_STATUS = {"in_stock", "low_stock", "out_of_stock", "unknown"}

NO_GO_BOUNDARIES = (
    "live_dropi",
    "external_writes",
    "spend",
    "fulfillment_automation",
    "order_placement",
    "inventory_reservation",
)


def _require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DropiFixtureValidationError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise DropiFixtureValidationError(f"{path} must be a list")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DropiFixtureValidationError(f"{path} must be a non-empty string")
    return value.strip()


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise DropiFixtureValidationError(f"{path} must be a boolean")
    return value


def _decimal_string(value: Any, path: str) -> str:
    raw = _require_string(value, path)
    try:
        parsed = Decimal(raw)
    except InvalidOperation as exc:
        raise DropiFixtureValidationError(f"{path} must be a decimal string") from exc
    if parsed < Decimal("0"):
        raise DropiFixtureValidationError(f"{path} must be non-negative")
    return str(parsed)


def _assert_false(value: Any, path: str) -> None:
    if _require_bool(value, path) is not False:
        raise DropiFixtureValidationError(f"{path} must be false")


def _assert_true(value: Any, path: str) -> None:
    if _require_bool(value, path) is not True:
        raise DropiFixtureValidationError(f"{path} must be true")


def validate_safety_block(safety: dict[str, Any], path: str = "safety") -> dict[str, Any]:
    safety = _require_dict(safety, path)

    _assert_true(safety.get("read_only"), f"{path}.read_only")
    _assert_false(safety.get("live_dropi"), f"{path}.live_dropi")
    _assert_false(safety.get("external_writes"), f"{path}.external_writes")
    _assert_false(safety.get("spend"), f"{path}.spend")
    _assert_false(safety.get("fulfillment_automation"), f"{path}.fulfillment_automation")
    _assert_false(safety.get("order_placement"), f"{path}.order_placement")
    _assert_false(safety.get("inventory_reservation"), f"{path}.inventory_reservation")
    _assert_true(safety.get("operator_review_required"), f"{path}.operator_review_required")

    return dict(safety)


def validate_dropi_fixture_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _require_dict(payload, "payload")

    metadata = _require_dict(payload.get("metadata"), "metadata")
    supplier = _require_dict(payload.get("supplier"), "supplier")
    products = _require_list(payload.get("products"), "products")
    root_safety = validate_safety_block(_require_dict(payload.get("safety"), "safety"), "safety")

    if not products:
        raise DropiFixtureValidationError("products must contain at least one product")

    normalized_metadata = {
        "fixture_id": _require_string(metadata.get("fixture_id"), "metadata.fixture_id"),
        "source": _require_string(metadata.get("source"), "metadata.source"),
        "captured_at": _require_string(metadata.get("captured_at"), "metadata.captured_at"),
        "currency": _require_string(metadata.get("currency"), "metadata.currency"),
        "country": _require_string(metadata.get("country"), "metadata.country"),
    }

    normalized_supplier = {
        "supplier_id": _require_string(supplier.get("supplier_id"), "supplier.supplier_id"),
        "supplier_name": _require_string(supplier.get("supplier_name"), "supplier.supplier_name"),
        "country": _require_string(supplier.get("country"), "supplier.country"),
        "platform": _require_string(supplier.get("platform"), "supplier.platform"),
        "rating": _require_string(str(supplier.get("rating", "unknown")), "supplier.rating"),
        "risk_flags": list(_require_list(supplier.get("risk_flags"), "supplier.risk_flags")),
        "read_only": _require_bool(supplier.get("read_only"), "supplier.read_only"),
    }

    if normalized_supplier["platform"] != "dropi_fixture":
        raise DropiFixtureValidationError("supplier.platform must be dropi_fixture")
    if normalized_supplier["read_only"] is not True:
        raise DropiFixtureValidationError("supplier.read_only must be true")

    normalized_products: list[dict[str, Any]] = []

    for idx, product_raw in enumerate(products):
        product_path = f"products[{idx}]"
        product = _require_dict(product_raw, product_path)

        inventory = _require_dict(product.get("inventory"), f"{product_path}.inventory")
        costs = _require_dict(product.get("costs"), f"{product_path}.costs")
        fulfillment = _require_dict(product.get("fulfillment"), f"{product_path}.fulfillment")
        safety = validate_safety_block(
            _require_dict(product.get("safety"), f"{product_path}.safety"),
            f"{product_path}.safety",
        )

        stock_status = _require_string(inventory.get("stock_status"), f"{product_path}.inventory.stock_status")
        if stock_status not in ALLOWED_STOCK_STATUS:
            raise DropiFixtureValidationError(f"{product_path}.inventory.stock_status is invalid")

        _assert_true(inventory.get("read_only"), f"{product_path}.inventory.read_only")
        _assert_false(inventory.get("inventory_reservation"), f"{product_path}.inventory.inventory_reservation")
        _assert_true(fulfillment.get("read_only"), f"{product_path}.fulfillment.read_only")
        _assert_false(fulfillment.get("order_placement_supported"), f"{product_path}.fulfillment.order_placement_supported")
        _assert_false(fulfillment.get("auto_fulfillment_enabled"), f"{product_path}.fulfillment.auto_fulfillment_enabled")

        normalized_products.append(
            {
                "supplier_product_id": _require_string(product.get("supplier_product_id"), f"{product_path}.supplier_product_id"),
                "supplier_sku": _require_string(product.get("supplier_sku"), f"{product_path}.supplier_sku"),
                "title": _require_string(product.get("title"), f"{product_path}.title"),
                "description": _require_string(product.get("description"), f"{product_path}.description"),
                "category": _require_string(product.get("category"), f"{product_path}.category"),
                "brand": _require_string(product.get("brand"), f"{product_path}.brand"),
                "images": list(_require_list(product.get("images"), f"{product_path}.images")),
                "tags": list(_require_list(product.get("tags"), f"{product_path}.tags")),
                "read_only": _require_bool(product.get("read_only"), f"{product_path}.read_only"),
                "inventory": {
                    "stock_status": stock_status,
                    "stock_quantity": inventory.get("stock_quantity"),
                    "warehouse_region": _require_string(inventory.get("warehouse_region"), f"{product_path}.inventory.warehouse_region"),
                    "last_seen_at": _require_string(inventory.get("last_seen_at"), f"{product_path}.inventory.last_seen_at"),
                    "inventory_reservation": False,
                    "read_only": True,
                },
                "costs": {
                    "supplier_cost": _decimal_string(costs.get("supplier_cost"), f"{product_path}.costs.supplier_cost"),
                    "currency": _require_string(costs.get("currency"), f"{product_path}.costs.currency"),
                    "shipping_cost_estimate": _decimal_string(costs.get("shipping_cost_estimate"), f"{product_path}.costs.shipping_cost_estimate"),
                    "fees_estimate": _decimal_string(costs.get("fees_estimate"), f"{product_path}.costs.fees_estimate"),
                    "min_margin_required": _decimal_string(costs.get("min_margin_required"), f"{product_path}.costs.min_margin_required"),
                },
                "fulfillment": {
                    "fulfillment_supported": _require_bool(fulfillment.get("fulfillment_supported"), f"{product_path}.fulfillment.fulfillment_supported"),
                    "estimated_delivery_days_min": int(fulfillment.get("estimated_delivery_days_min")),
                    "estimated_delivery_days_max": int(fulfillment.get("estimated_delivery_days_max")),
                    "shipping_provider": _require_string(fulfillment.get("shipping_provider"), f"{product_path}.fulfillment.shipping_provider"),
                    "order_placement_supported": False,
                    "auto_fulfillment_enabled": False,
                    "read_only": True,
                },
                "safety": safety,
            }
        )

        if normalized_products[-1]["read_only"] is not True:
            raise DropiFixtureValidationError(f"{product_path}.read_only must be true")

    return {
        "metadata": normalized_metadata,
        "supplier": normalized_supplier,
        "products": normalized_products,
        "safety": root_safety,
    }


def load_dropi_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return validate_dropi_fixture_payload(payload)


def build_supplier_surface(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_dropi_fixture_payload(payload)
    products = normalized["products"]
    return {
        "read_only": True,
        "external_side_effects": False,
        "supplier_id": normalized["supplier"]["supplier_id"],
        "supplier_name": normalized["supplier"]["supplier_name"],
        "platform": normalized["supplier"]["platform"],
        "product_count": len(products),
        "in_stock_count": sum(1 for item in products if item["inventory"]["stock_status"] == "in_stock"),
        "low_stock_count": sum(1 for item in products if item["inventory"]["stock_status"] == "low_stock"),
        "out_of_stock_count": sum(1 for item in products if item["inventory"]["stock_status"] == "out_of_stock"),
        "operator_review_required": True,
        "boundaries": {
            "live_dropi": False,
            "external_writes": False,
            "spend": False,
            "fulfillment_automation": False,
            "order_placement": False,
            "inventory_reservation": False,
        },
    }


def dropi_product_to_financial_candidate(
    product: dict[str, Any],
    supplier: dict[str, Any],
) -> dict[str, Any]:
    product = _require_dict(product, "product")
    supplier = _require_dict(supplier, "supplier")

    costs = _require_dict(product.get("costs"), "product.costs")
    inventory = _require_dict(product.get("inventory"), "product.inventory")
    safety = validate_safety_block(_require_dict(product.get("safety"), "product.safety"), "product.safety")

    return {
        "candidate_id": _require_string(product.get("supplier_product_id"), "product.supplier_product_id"),
        "source": "dropi_fixture",
        "title": _require_string(product.get("title"), "product.title"),
        "category": _require_string(product.get("category"), "product.category"),
        "supplier": {
            "supplier_id": _require_string(supplier.get("supplier_id"), "supplier.supplier_id"),
            "supplier_name": _require_string(supplier.get("supplier_name"), "supplier.supplier_name"),
            "platform": "dropi_fixture",
        },
        "costs": {
            "product_cost": _decimal_string(costs.get("supplier_cost"), "product.costs.supplier_cost"),
            "shipping_cost_estimate": _decimal_string(costs.get("shipping_cost_estimate"), "product.costs.shipping_cost_estimate"),
            "fees_estimate": _decimal_string(costs.get("fees_estimate"), "product.costs.fees_estimate"),
            "currency": _require_string(costs.get("currency"), "product.costs.currency"),
            "min_margin_required": _decimal_string(costs.get("min_margin_required"), "product.costs.min_margin_required"),
        },
        "inventory": {
            "stock_status": _require_string(inventory.get("stock_status"), "product.inventory.stock_status"),
            "stock_quantity": inventory.get("stock_quantity"),
            "inventory_reservation": False,
        },
        "safety": {
            **safety,
            "external_side_effects": False,
        },
        "operator_review_required": True,
    }


__all__ = [
    "DropiFixtureValidationError",
    "NO_GO_BOUNDARIES",
    "build_supplier_surface",
    "dropi_product_to_financial_candidate",
    "load_dropi_fixture",
    "validate_dropi_fixture_payload",
    "validate_safety_block",
]