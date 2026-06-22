from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from synapse.financial import FinancialInput, FinancialResult, evaluate_financials
from synapse.integration.dropi_fixture_readonly import (
    DropiFixtureValidationError,
    dropi_product_to_financial_candidate,
)


class DropiFinancialBridgeError(ValueError):
    """Raised when a Dropi read-only candidate cannot enter financial evaluation safely."""


_FALSE_SAFETY_FLAGS = (
    "live_dropi",
    "external_writes",
    "spend",
    "fulfillment_automation",
    "order_placement",
    "inventory_reservation",
)


_BOUNDARIES = {
    "live_dropi": False,
    "external_writes": False,
    "spend": False,
    "fulfillment_automation": False,
    "order_placement": False,
    "inventory_reservation": False,
}


def dropi_candidate_to_financial_input(
    candidate: Mapping[str, Any],
    *,
    price: Decimal | str,
    estimated_cac: Decimal | str,
    expected_units: int = 1,
) -> FinancialInput:
    """Map a local Dropi fixture candidate into the existing FinancialInput contract.

    Selling price, CAC, and expected units are explicit operator assumptions.
    Dropi supplier data contributes only local read-only cost/supplier signals.
    """

    candidate = _require_mapping(candidate, "candidate")
    _assert_safe_dropi_candidate(candidate)

    costs = _require_mapping(candidate.get("costs"), "candidate.costs")

    product_cost = _decimal(costs.get("product_cost"), "candidate.costs.product_cost")
    shipping_cost = _decimal(costs.get("shipping_cost_estimate"), "candidate.costs.shipping_cost_estimate")
    fees = _decimal(costs.get("fees_estimate"), "candidate.costs.fees_estimate")

    landed_cost = product_cost + shipping_cost + fees
    if landed_cost <= Decimal("0"):
        raise DropiFinancialBridgeError("landed_cost must be positive")

    values: dict[str, Any] = {
        "candidate_id": _require_string(candidate.get("candidate_id"), "candidate.candidate_id"),
        "product_id": _require_string(candidate.get("candidate_id"), "candidate.candidate_id"),
        "id": _require_string(candidate.get("candidate_id"), "candidate.candidate_id"),
        "title": _require_string(candidate.get("title"), "candidate.title"),
        "name": _require_string(candidate.get("title"), "candidate.title"),
        "product_title": _require_string(candidate.get("title"), "candidate.title"),
        "category": _require_string(candidate.get("category"), "candidate.category"),
        "price": _positive_decimal(price, "price"),
        "landed_cost": _money(landed_cost),
        "estimated_cac": _non_negative_decimal(estimated_cac, "estimated_cac"),
        "expected_units": _positive_int(expected_units, "expected_units"),
    }

    return _build_financial_input(values)


def evaluate_dropi_candidate_financials(
    product: Mapping[str, Any],
    supplier: Mapping[str, Any],
    *,
    price: Decimal | str,
    estimated_cac: Decimal | str,
    expected_units: int = 1,
) -> dict[str, Any]:
    """Build and evaluate a read-only Dropi fixture candidate through SYNAPSE financials."""

    candidate = dropi_product_to_financial_candidate(dict(product), dict(supplier))
    financial_input = dropi_candidate_to_financial_input(
        candidate,
        price=price,
        estimated_cac=estimated_cac,
        expected_units=expected_units,
    )
    financial_result = evaluate_financials(financial_input)

    return {
        "read_only": True,
        "external_side_effects": False,
        "source": "dropi_fixture",
        "target": "synapse.financial.evaluation.FinancialInput",
        "candidate": candidate,
        "financial_input": financial_input,
        "financial_result": financial_result,
        "operator_review_required": True,
        "boundaries": dict(_BOUNDARIES),
    }


def _build_financial_input(values: Mapping[str, Any]) -> FinancialInput:
    if not is_dataclass(FinancialInput):
        raise DropiFinancialBridgeError("FinancialInput must remain a dataclass contract")

    kwargs: dict[str, Any] = {}
    missing_required: list[str] = []

    for field in fields(FinancialInput):
        if not field.init:
            continue
        if field.name in values:
            kwargs[field.name] = values[field.name]
            continue
        if field.default is MISSING and field.default_factory is MISSING:  # type: ignore[attr-defined]
            missing_required.append(field.name)

    if missing_required:
        joined = ", ".join(sorted(missing_required))
        raise DropiFinancialBridgeError(f"Unsupported FinancialInput required fields: {joined}")

    return FinancialInput(**kwargs)


def _assert_safe_dropi_candidate(candidate: Mapping[str, Any]) -> None:
    source = candidate.get("source")
    if source != "dropi_fixture":
        raise DropiFinancialBridgeError("candidate.source must be dropi_fixture")

    if candidate.get("operator_review_required") is not True:
        raise DropiFinancialBridgeError("candidate.operator_review_required must be true")

    safety = _require_mapping(candidate.get("safety"), "candidate.safety")

    if safety.get("read_only") is not True:
        raise DropiFinancialBridgeError("candidate.safety.read_only must be true")
    if safety.get("external_side_effects") is not False:
        raise DropiFinancialBridgeError("candidate.safety.external_side_effects must be false")

    for flag in _FALSE_SAFETY_FLAGS:
        if safety.get(flag) is not False:
            raise DropiFinancialBridgeError(f"candidate.safety.{flag} must be false")


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DropiFinancialBridgeError(f"{path} must be a mapping")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DropiFinancialBridgeError(f"{path} must be a non-empty string")
    return value


def _decimal(value: Any, path: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DropiFinancialBridgeError(f"{path} must be a decimal value") from exc

    if not parsed.is_finite():
        raise DropiFinancialBridgeError(f"{path} must be finite")

    return parsed


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _positive_decimal(value: Any, path: str) -> Decimal:
    parsed = _decimal(value, path)
    if parsed <= Decimal("0"):
        raise DropiFinancialBridgeError(f"{path} must be positive")
    return _money(parsed)


def _non_negative_decimal(value: Any, path: str) -> Decimal:
    parsed = _decimal(value, path)
    if parsed < Decimal("0"):
        raise DropiFinancialBridgeError(f"{path} must be non-negative")
    return _money(parsed)


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool):
        raise DropiFinancialBridgeError(f"{path} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DropiFinancialBridgeError(f"{path} must be a positive integer") from exc

    if parsed <= 0:
        raise DropiFinancialBridgeError(f"{path} must be a positive integer")

    return parsed


__all__ = [
    "DropiFinancialBridgeError",
    "dropi_candidate_to_financial_input",
    "evaluate_dropi_candidate_financials",
]