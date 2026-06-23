"""A8-R93 Dropi read-only evaluated product shortlist.

This module ranks Dropi fixture products through the A8-R92 financial bridge.
It is fixture/local/read-only only. It performs no network IO, external writes,
spend, order placement, fulfillment, inventory reservation, or credential IO.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from synapse.integration.dropi_fixture_readonly import (
    build_supplier_surface,
    load_dropi_fixture,
)
from synapse.integration.dropi_to_financial_evaluation import (
    evaluate_dropi_candidate_financials,
)

Evaluator = Callable[..., dict[str, Any]]

_BOUNDARIES: dict[str, bool] = {
    "fixture_only": True,
    "local_only": True,
    "read_only": True,
    "live_dropi": False,
    "live_shopify": False,
    "live_meta": False,
    "network_io": False,
    "external_writes": False,
    "spend": False,
    "order_placement": False,
    "fulfillment_automation": False,
    "inventory_reservation": False,
    "credentials": False,
}

_SCORE_VERSION = "dropi_evaluated_shortlist_v1"


class DropiShortlistError(ValueError):
    """Raised when shortlist inputs violate the read-only fixture contract."""


def build_dropi_evaluated_shortlist_from_fixture(
    path: str | Path,
    *,
    price: Any,
    estimated_cac: Any,
    expected_units: Any = 1,
    max_items: Any = 5,
    min_contribution_profit: Any = Decimal("0.00"),
) -> dict[str, Any]:
    """Load a Dropi fixture and build a deterministic evaluated shortlist."""

    payload = load_dropi_fixture(Path(path))
    return build_dropi_evaluated_shortlist(
        payload,
        price=price,
        estimated_cac=estimated_cac,
        expected_units=expected_units,
        max_items=max_items,
        min_contribution_profit=min_contribution_profit,
    )


def build_dropi_evaluated_shortlist(
    payload: Mapping[str, Any],
    *,
    price: Any,
    estimated_cac: Any,
    expected_units: Any = 1,
    max_items: Any = 5,
    min_contribution_profit: Any = Decimal("0.00"),
    evaluator: Evaluator = evaluate_dropi_candidate_financials,
) -> dict[str, Any]:
    """Evaluate multiple Dropi fixture products and return a ranked shortlist."""

    _require_mapping(payload, "payload")
    operator_price = _positive_decimal(price, "price")
    operator_cac = _non_negative_decimal(estimated_cac, "estimated_cac")
    units = _positive_int(expected_units, "expected_units")
    limit = _positive_int(max_items, "max_items")
    min_profit = _decimal(min_contribution_profit, "min_contribution_profit")

    surface = build_supplier_surface(payload)
    supplier = _first_mapping(
        (surface.get("supplier"), payload.get("supplier")),
        "supplier",
    )
    products_value = _first_sequence(
        (surface.get("products"), payload.get("products")),
        "products",
    )

    assumptions = {
        "price": _money(operator_price),
        "estimated_cac": _money(operator_cac),
        "expected_units": units,
        "max_items": limit,
        "min_contribution_profit": _money(min_profit),
    }

    ranked_candidates: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []

    for index, product_value in enumerate(products_value):
        product_ref = _product_ref(product_value, index)

        if not isinstance(product_value, Mapping):
            rejections.append(
                _rejection(
                    product_ref=product_ref,
                    code="INVALID_PRODUCT_CONTRACT",
                    reason=f"product is not a mapping: {type(product_value).__name__}",
                )
            )
            continue

        try:
            bridge_payload = evaluator(
                product=product_value,
                supplier=supplier,
                price=operator_price,
                estimated_cac=operator_cac,
                expected_units=units,
            )
            candidate = _build_ranked_candidate(
                product=product_value,
                supplier=supplier,
                bridge_payload=bridge_payload,
                assumptions=assumptions,
            )
        except Exception as exc:
            rejections.append(
                _rejection(
                    product_ref=product_ref,
                    code="BRIDGE_FAIL_CLOSED",
                    reason=f"{exc.__class__.__name__}: {exc}",
                )
            )
            continue

        contribution_profit = _decimal(candidate["score"]["contribution_profit"], "candidate.score.contribution_profit")
        if contribution_profit < min_profit:
            rejections.append(
                _rejection(
                    product_ref=product_ref,
                    code="BELOW_MIN_CONTRIBUTION_PROFIT",
                    reason=(
                        "contribution_profit "
                        f"{_money(contribution_profit)} < minimum {_money(min_profit)}"
                    ),
                )
            )
            continue

        ranked_candidates.append(candidate)

    ranked_candidates = sorted(ranked_candidates, key=_ranking_key)
    shortlist = ranked_candidates[:limit]

    for rank, item in enumerate(shortlist, start=1):
        item["rank"] = rank

    return {
        "source": {
            "type": "dropi_fixture",
            "contract": "A8-R91",
        },
        "target": {
            "type": "dropi_evaluated_product_shortlist",
            "contract": "A8-R93",
            "score_version": _SCORE_VERSION,
        },
        "assumptions": assumptions,
        "summary": {
            "input_product_count": len(products_value),
            "evaluated_product_count": len(ranked_candidates) + len(
                [r for r in rejections if r["code"] == "BELOW_MIN_CONTRIBUTION_PROFIT"]
            ),
            "shortlist_count": len(shortlist),
            "rejection_count": len(rejections),
            "operator_review_required": True,
        },
        "shortlist": shortlist,
        "rejections": rejections,
        "operator_review_required": True,
        "boundaries": dict(_BOUNDARIES),
    }


def _build_ranked_candidate(
    *,
    product: Mapping[str, Any],
    supplier: Mapping[str, Any],
    bridge_payload: Mapping[str, Any],
    assumptions: Mapping[str, Any],
) -> dict[str, Any]:
    _require_mapping(bridge_payload, "bridge_payload")

    financial_input = _to_plain_mapping(bridge_payload.get("financial_input"), "bridge_payload.financial_input")
    financial_result = _to_plain_mapping(bridge_payload.get("financial_result"), "bridge_payload.financial_result")
    candidate = _to_plain_mapping(bridge_payload.get("candidate"), "bridge_payload.candidate")
    boundaries = _to_plain_mapping(bridge_payload.get("boundaries"), "bridge_payload.boundaries")

    if bridge_payload.get("operator_review_required") is not True:
        raise DropiShortlistError("bridge_payload.operator_review_required must be true")

    price = _first_decimal(
        financial_input,
        ("price", "selling_price", "unit_price"),
        fallback=_decimal(assumptions["price"], "assumptions.price"),
    )
    landed_cost = _first_decimal(
        financial_input,
        ("landed_cost", "unit_landed_cost", "cost", "total_cost"),
        fallback=_candidate_landed_cost(candidate),
    )
    estimated_cac = _first_decimal(
        financial_input,
        ("estimated_cac", "cac", "customer_acquisition_cost"),
        fallback=_decimal(assumptions["estimated_cac"], "assumptions.estimated_cac"),
    )

    contribution_profit = price - landed_cost - estimated_cac
    margin_rate = Decimal("0.00") if price == 0 else contribution_profit / price

    product_id = _optional_string(product.get("product_id") or product.get("id"))
    sku = _optional_string(product.get("sku"))
    title = _optional_string(product.get("title") or product.get("name"))
    supplier_id = _optional_string(supplier.get("supplier_id") or supplier.get("id"))
    supplier_name = _optional_string(supplier.get("supplier_name") or supplier.get("name"))

    return {
        "rank": None,
        "product": {
            "product_id": product_id,
            "sku": sku,
            "title": title,
        },
        "supplier": {
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
        },
        "score": {
            "score_version": _SCORE_VERSION,
            "price": _money(price),
            "landed_cost": _money(landed_cost),
            "estimated_cac": _money(estimated_cac),
            "contribution_profit": _money(contribution_profit),
            "margin_rate": _ratio(margin_rate),
        },
        "source": _to_plain(bridge_payload.get("source")),
        "target": _to_plain(bridge_payload.get("target")),
        "candidate": candidate,
        "financial_input": financial_input,
        "financial_result": financial_result,
        "bridge_boundaries": boundaries,
        "operator_review_required": True,
        "boundaries": dict(_BOUNDARIES),
    }


def _ranking_key(item: Mapping[str, Any]) -> tuple[Decimal, Decimal, str, str, str]:
    score = _require_mapping(item.get("score"), "item.score")
    contribution_profit = _decimal(score.get("contribution_profit"), "score.contribution_profit")
    margin_rate = _decimal(score.get("margin_rate"), "score.margin_rate")
    product = _require_mapping(item.get("product"), "item.product")
    supplier = _require_mapping(item.get("supplier"), "item.supplier")
    return (
        -contribution_profit,
        -margin_rate,
        str(product.get("sku") or ""),
        str(product.get("product_id") or ""),
        str(supplier.get("supplier_id") or ""),
    )


def _rejection(*, product_ref: Mapping[str, Any], code: str, reason: str) -> dict[str, Any]:
    return {
        "status": "rejected_fail_closed",
        "code": _require_string(code, "code"),
        "reason": _require_string(reason, "reason"),
        "product": dict(product_ref),
        "operator_review_required": True,
        "boundaries": dict(_BOUNDARIES),
    }


def _product_ref(product: Any, index: int) -> dict[str, Any]:
    if isinstance(product, Mapping):
        return {
            "index": index,
            "product_id": _optional_string(product.get("product_id") or product.get("id")),
            "sku": _optional_string(product.get("sku")),
            "title": _optional_string(product.get("title") or product.get("name")),
        }
    return {
        "index": index,
        "product_id": None,
        "sku": None,
        "title": None,
    }


def _candidate_landed_cost(candidate: Mapping[str, Any]) -> Decimal:
    costs = _require_mapping(candidate.get("costs"), "candidate.costs")
    product_cost = _decimal(costs.get("product_cost"), "candidate.costs.product_cost")
    shipping_cost = _decimal(costs.get("shipping_cost_estimate"), "candidate.costs.shipping_cost_estimate")
    fees = _decimal(costs.get("fees_estimate"), "candidate.costs.fees_estimate")
    return product_cost + shipping_cost + fees


def _to_plain_mapping(value: Any, path: str) -> dict[str, Any]:
    plain = _to_plain(value)
    if not isinstance(plain, Mapping):
        raise DropiShortlistError(f"{path} must normalize to a mapping")
    return {str(k): v for k, v in plain.items()}


def _to_plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _to_plain(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    if isinstance(value, tuple):
        return [_to_plain(v) for v in value]
    if isinstance(value, Decimal):
        return _money(value)
    return value


def _first_decimal(values: Mapping[str, Any], names: Sequence[str], *, fallback: Decimal) -> Decimal:
    for name in names:
        if name in values and values[name] is not None:
            return _decimal(values[name], f"values.{name}")
    return fallback


def _first_mapping(values: Sequence[Any], path: str) -> Mapping[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return value
    raise DropiShortlistError(f"{path} must contain a mapping")


def _first_sequence(values: Sequence[Any], path: str) -> Sequence[Any]:
    for value in values:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return value
    raise DropiShortlistError(f"{path} must contain a product sequence")


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DropiShortlistError(f"{path} must be a mapping")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DropiShortlistError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool):
        raise DropiShortlistError(f"{path} must be a positive integer")
    if not isinstance(value, int):
        raise DropiShortlistError(f"{path} must be a positive integer")
    if value <= 0:
        raise DropiShortlistError(f"{path} must be positive")
    return value


def _decimal(value: Any, path: str) -> Decimal:
    if isinstance(value, bool):
        raise DropiShortlistError(f"{path} must be decimal-compatible")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DropiShortlistError(f"{path} must be decimal-compatible") from exc


def _positive_decimal(value: Any, path: str) -> Decimal:
    result = _decimal(value, path)
    if result <= 0:
        raise DropiShortlistError(f"{path} must be positive")
    return result


def _non_negative_decimal(value: Any, path: str) -> Decimal:
    result = _decimal(value, path)
    if result < 0:
        raise DropiShortlistError(f"{path} must be non-negative")
    return result


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _ratio(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))