"""SYNAPSE Product Decision Engine.

This module provides a deterministic, auditable product selection contract.

Design rule:
    The operator defines constraints.
    The system scores candidates.
    Manual product picking is not the primary flow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


ENGINE_VERSION = "A8-R31.product-decision-engine.v1"

DEFAULT_CONSTRAINTS: dict[str, float] = {
    "min_gross_margin_pct": 35.0,
    "max_shipping_days": 12.0,
    "min_supplier_score": 70.0,
    "min_demand_score": 55.0,
    "min_content_fit_score": 50.0,
    "min_problem_severity_score": 45.0,
    "max_saturation_score": 75.0,
    "max_compliance_risk_score": 25.0,
    "max_return_risk_score": 55.0,
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "demand": 0.20,
    "gross_margin": 0.18,
    "content_fit": 0.17,
    "problem_severity": 0.14,
    "competition": 0.12,
    "operational": 0.11,
    "risk": 0.08,
}

REQUIRED_CANDIDATE_FIELDS = (
    "sku",
    "name",
    "niche",
    "landed_cost",
    "sell_price",
    "shipping_days",
    "supplier_score",
    "demand_score",
    "saturation_score",
    "content_fit_score",
    "problem_severity_score",
    "compliance_risk_score",
    "return_risk_score",
)


@dataclass(frozen=True)
class ProductCandidate:
    sku: str
    name: str
    niche: str
    landed_cost: float
    sell_price: float
    shipping_days: float
    supplier_score: float
    demand_score: float
    saturation_score: float
    content_fit_score: float
    problem_severity_score: float
    compliance_risk_score: float
    return_risk_score: float

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ProductCandidate":
        missing = [field for field in REQUIRED_CANDIDATE_FIELDS if field not in raw]
        if missing:
            raise ValueError(f"missing candidate fields: {missing}")

        sku = _require_non_empty_string(raw, "sku")
        name = _require_non_empty_string(raw, "name")
        niche = _require_non_empty_string(raw, "niche")

        return cls(
            sku=sku,
            name=name,
            niche=niche,
            landed_cost=_require_number(raw, "landed_cost", min_value=0.01),
            sell_price=_require_number(raw, "sell_price", min_value=0.01),
            shipping_days=_require_number(raw, "shipping_days", min_value=0.0),
            supplier_score=_require_number(raw, "supplier_score", min_value=0.0, max_value=100.0),
            demand_score=_require_number(raw, "demand_score", min_value=0.0, max_value=100.0),
            saturation_score=_require_number(raw, "saturation_score", min_value=0.0, max_value=100.0),
            content_fit_score=_require_number(raw, "content_fit_score", min_value=0.0, max_value=100.0),
            problem_severity_score=_require_number(raw, "problem_severity_score", min_value=0.0, max_value=100.0),
            compliance_risk_score=_require_number(raw, "compliance_risk_score", min_value=0.0, max_value=100.0),
            return_risk_score=_require_number(raw, "return_risk_score", min_value=0.0, max_value=100.0),
        )


def evaluate_product_candidate(
    candidate: Mapping[str, Any],
    *,
    constraints: Mapping[str, float] | None = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate one product candidate and return an auditable decision packet."""

    resolved_constraints = _merge_constraints(constraints)
    resolved_weights = _merge_weights(weights)
    product = ProductCandidate.from_mapping(candidate)

    gross_margin_pct = _gross_margin_pct(product)
    shipping_score = _shipping_score(
        product.shipping_days,
        max_shipping_days=resolved_constraints["max_shipping_days"],
    )
    gross_margin_score = _clamp((gross_margin_pct / 60.0) * 100.0)
    competition_score = _clamp(100.0 - product.saturation_score)
    operational_score = _clamp((product.supplier_score * 0.60) + (shipping_score * 0.40))
    risk_score = _clamp(
        100.0 - ((product.compliance_risk_score * 0.60) + (product.return_risk_score * 0.40))
    )

    score_components = {
        "demand": _round(product.demand_score),
        "gross_margin": _round(gross_margin_score),
        "content_fit": _round(product.content_fit_score),
        "problem_severity": _round(product.problem_severity_score),
        "competition": _round(competition_score),
        "operational": _round(operational_score),
        "risk": _round(risk_score),
    }

    total_score = _round(
        sum(score_components[key] * resolved_weights[key] for key in DEFAULT_WEIGHTS)
    )

    block_reasons = _block_reasons(product, gross_margin_pct, resolved_constraints)
    decision = "PASS" if not block_reasons else "BLOCK"

    return {
        "engine_version": ENGINE_VERSION,
        "sku": product.sku,
        "name": product.name,
        "niche": product.niche,
        "decision": decision,
        "score": total_score,
        "gross_margin_pct": _round(gross_margin_pct),
        "score_components": score_components,
        "block_reasons": block_reasons,
        "candidate": asdict(product),
        "audit": {
            "manual_selection_used": False,
            "selection_mode": "system_scored",
            "operator_role": "strategy_constraints_and_gate_approval",
        },
    }


def select_product_candidates(
    candidates: list[Mapping[str, Any]],
    *,
    constraints: Mapping[str, float] | None = None,
    weights: Mapping[str, float] | None = None,
    backup_count: int = 3,
) -> dict[str, Any]:
    """Select champion and backups deterministically from candidate data."""

    if not candidates:
        raise ValueError("candidates must not be empty")

    if backup_count < 0:
        raise ValueError("backup_count must be >= 0")

    resolved_constraints = _merge_constraints(constraints)
    resolved_weights = _merge_weights(weights)

    evaluated = [
        evaluate_product_candidate(
            candidate,
            constraints=resolved_constraints,
            weights=resolved_weights,
        )
        for candidate in candidates
    ]

    passing = [item for item in evaluated if item["decision"] == "PASS"]
    rejected = [item for item in evaluated if item["decision"] == "BLOCK"]

    ranked = sorted(
        passing,
        key=lambda item: (-item["score"], item["sku"], item["name"]),
    )

    champion = ranked[0] if ranked else None
    backups = ranked[1 : 1 + backup_count]

    return {
        "engine_version": ENGINE_VERSION,
        "decision_type": "product_candidate_selection",
        "selection_mode": "system_scored",
        "manual_selection_used": False,
        "champion": champion,
        "backups": backups,
        "ranked_candidates": ranked,
        "rejected_candidates": rejected,
        "counts": {
            "input": len(candidates),
            "passed": len(passing),
            "blocked": len(rejected),
            "backups": len(backups),
        },
        "constraints": dict(resolved_constraints),
        "weights": dict(resolved_weights),
        "acceptance": {
            "has_champion": champion is not None,
            "champion_explainable": champion is not None and bool(champion["score_components"]),
            "manual_selection_blocked_as_primary_flow": True,
        },
    }


def _block_reasons(
    product: ProductCandidate,
    gross_margin_pct: float,
    constraints: Mapping[str, float],
) -> list[str]:
    reasons: list[str] = []

    if gross_margin_pct < constraints["min_gross_margin_pct"]:
        reasons.append("gross_margin_below_minimum")

    if product.shipping_days > constraints["max_shipping_days"]:
        reasons.append("shipping_days_above_maximum")

    if product.supplier_score < constraints["min_supplier_score"]:
        reasons.append("supplier_score_below_minimum")

    if product.demand_score < constraints["min_demand_score"]:
        reasons.append("demand_score_below_minimum")

    if product.content_fit_score < constraints["min_content_fit_score"]:
        reasons.append("content_fit_score_below_minimum")

    if product.problem_severity_score < constraints["min_problem_severity_score"]:
        reasons.append("problem_severity_score_below_minimum")

    if product.saturation_score > constraints["max_saturation_score"]:
        reasons.append("saturation_score_above_maximum")

    if product.compliance_risk_score > constraints["max_compliance_risk_score"]:
        reasons.append("compliance_risk_score_above_maximum")

    if product.return_risk_score > constraints["max_return_risk_score"]:
        reasons.append("return_risk_score_above_maximum")

    return reasons


def _merge_constraints(overrides: Mapping[str, float] | None) -> dict[str, float]:
    resolved = dict(DEFAULT_CONSTRAINTS)

    if overrides:
        for key, value in overrides.items():
            if key not in resolved:
                raise ValueError(f"unknown constraint: {key}")
            resolved[key] = _as_float(value, key)

    return resolved


def _merge_weights(overrides: Mapping[str, float] | None) -> dict[str, float]:
    resolved = dict(DEFAULT_WEIGHTS)

    if overrides:
        for key, value in overrides.items():
            if key not in resolved:
                raise ValueError(f"unknown weight: {key}")
            resolved[key] = _as_float(value, key)

    total = sum(resolved.values())
    if not (0.999 <= total <= 1.001):
        raise ValueError(f"weights must sum to 1.0, actual={total}")

    if any(value < 0 for value in resolved.values()):
        raise ValueError("weights must be non-negative")

    return resolved


def _require_non_empty_string(raw: Mapping[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{key} must not be empty")
    return cleaned


def _require_number(
    raw: Mapping[str, Any],
    key: str,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    value = _as_float(raw[key], key)

    if min_value is not None and value < min_value:
        raise ValueError(f"{key} must be >= {min_value}")

    if max_value is not None and value > max_value:
        raise ValueError(f"{key} must be <= {max_value}")

    return value


def _as_float(value: Any, key: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{key} must be numeric, not bool")

    if not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")

    return float(value)


def _gross_margin_pct(product: ProductCandidate) -> float:
    if product.sell_price <= 0:
        raise ValueError("sell_price must be > 0")
    return ((product.sell_price - product.landed_cost) / product.sell_price) * 100.0


def _shipping_score(shipping_days: float, *, max_shipping_days: float) -> float:
    if max_shipping_days <= 0:
        raise ValueError("max_shipping_days must be > 0")

    if shipping_days <= 3.0:
        return 100.0

    if shipping_days >= max_shipping_days:
        return 0.0

    usable_range = max_shipping_days - 3.0
    used_range = shipping_days - 3.0
    return _clamp(100.0 - ((used_range / usable_range) * 100.0))


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _round(value: float) -> float:
    return round(float(value), 4)
