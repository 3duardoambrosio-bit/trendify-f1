"""Synthetic discovery schema for SYNAPSE sandbox product candidates.

A8-R67 scope:
- deterministic local product candidates
- JSON-ready contract
- no network access
- no scraping
- no live commerce platform reads or writes
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

DISCOVERY_SCHEMA_VERSION = "a8-r67-synthetic-discovery-v1"
SYNTHETIC_SOURCE_TYPE = "synthetic"


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_candidate_id(payload: Mapping[str, Any], *, prefix: str = "disc", length: int = 14) -> str:
    raw = _stable_json(payload).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:length]
    return f"{prefix}_{digest}"


def calculate_margin_pct(price: int, cost: int) -> float:
    if int(price) <= 0:
        return 0.0
    return round((int(price) - int(cost)) / int(price), 4)


@dataclass(frozen=True)
class DiscoverySignal:
    name: str
    score: float
    rationale: str
    kind: str

    def __post_init__(self) -> None:
        name = _clean_text(self.name)
        rationale = _clean_text(self.rationale)
        kind = _clean_text(self.kind)

        if not name:
            raise ValueError("DiscoverySignal.name is required")
        if not rationale:
            raise ValueError("DiscoverySignal.rationale is required")
        if kind not in {"demand", "risk", "differentiation"}:
            raise ValueError(f"Unsupported DiscoverySignal.kind={kind!r}")
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError("DiscoverySignal.score must be between 0 and 1")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "score", round(float(self.score), 4))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_signal(value: DiscoverySignal | Mapping[str, Any], *, fallback_kind: str) -> DiscoverySignal:
    if isinstance(value, DiscoverySignal):
        return value
    if isinstance(value, Mapping):
        return DiscoverySignal(
            name=str(value.get("name", "")),
            score=float(value.get("score", 0.0)),
            rationale=str(value.get("rationale", "")),
            kind=str(value.get("kind", fallback_kind)),
        )
    raise TypeError(f"Unsupported signal value: {type(value).__name__}")


def _coerce_signal_tuple(
    values: tuple[DiscoverySignal | Mapping[str, Any], ...] | list[DiscoverySignal | Mapping[str, Any]],
    *,
    fallback_kind: str,
) -> tuple[DiscoverySignal, ...]:
    return tuple(_coerce_signal(value, fallback_kind=fallback_kind) for value in values)


@dataclass(frozen=True)
class DiscoveryCandidate:
    candidate_id: str
    product_name: str
    category: str
    market: str
    price: int
    cost: int
    margin_pct: float
    source_type: str
    demand_signals: tuple[DiscoverySignal, ...]
    risk_signals: tuple[DiscoverySignal, ...]
    differentiation_signals: tuple[DiscoverySignal, ...]
    evidence_notes: tuple[str, ...]
    created_by_version: str = DISCOVERY_SCHEMA_VERSION
    supplier_mode: str = "sandbox_synthetic_supplier"
    traffic: int = 800
    days: int = 3
    marketing_angle: str = ""
    primary_hook: str = ""
    target_audience: str = ""
    use_case: str = ""

    def __post_init__(self) -> None:
        product_name = _clean_text(self.product_name)
        category = _clean_text(self.category)
        market = _clean_text(self.market).upper()
        candidate_id = _clean_text(self.candidate_id)
        source_type = _clean_text(self.source_type)
        created_by_version = _clean_text(self.created_by_version)

        if not candidate_id:
            raise ValueError("DiscoveryCandidate.candidate_id is required")
        if not product_name:
            raise ValueError("DiscoveryCandidate.product_name is required")
        if not category:
            raise ValueError("DiscoveryCandidate.category is required")
        if not market:
            raise ValueError("DiscoveryCandidate.market is required")
        if source_type != SYNTHETIC_SOURCE_TYPE:
            raise ValueError("DiscoveryCandidate.source_type must be synthetic")
        if created_by_version != DISCOVERY_SCHEMA_VERSION:
            raise ValueError("DiscoveryCandidate.created_by_version mismatch")
        if int(self.price) <= 0:
            raise ValueError("DiscoveryCandidate.price must be positive")
        if int(self.cost) < 0:
            raise ValueError("DiscoveryCandidate.cost cannot be negative")

        expected_margin = calculate_margin_pct(int(self.price), int(self.cost))
        if round(float(self.margin_pct), 4) != expected_margin:
            raise ValueError(
                f"DiscoveryCandidate.margin_pct mismatch expected={expected_margin} actual={self.margin_pct}"
            )

        demand_signals = _coerce_signal_tuple(self.demand_signals, fallback_kind="demand")
        risk_signals = _coerce_signal_tuple(self.risk_signals, fallback_kind="risk")
        differentiation_signals = _coerce_signal_tuple(
            self.differentiation_signals,
            fallback_kind="differentiation",
        )

        if not demand_signals:
            raise ValueError("DiscoveryCandidate requires at least one demand signal")
        if not risk_signals:
            raise ValueError("DiscoveryCandidate requires at least one risk signal")
        if not differentiation_signals:
            raise ValueError("DiscoveryCandidate requires at least one differentiation signal")

        evidence_notes = tuple(_clean_text(note) for note in self.evidence_notes if _clean_text(note))
        if not evidence_notes:
            raise ValueError("DiscoveryCandidate requires evidence_notes")

        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "product_name", product_name)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "market", market)
        object.__setattr__(self, "price", int(self.price))
        object.__setattr__(self, "cost", int(self.cost))
        object.__setattr__(self, "margin_pct", expected_margin)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "demand_signals", demand_signals)
        object.__setattr__(self, "risk_signals", risk_signals)
        object.__setattr__(self, "differentiation_signals", differentiation_signals)
        object.__setattr__(self, "evidence_notes", evidence_notes)
        object.__setattr__(self, "created_by_version", created_by_version)
        object.__setattr__(self, "supplier_mode", _clean_text(self.supplier_mode))
        object.__setattr__(self, "traffic", int(self.traffic))
        object.__setattr__(self, "days", int(self.days))
        object.__setattr__(self, "marketing_angle", _clean_text(self.marketing_angle))
        object.__setattr__(self, "primary_hook", _clean_text(self.primary_hook))
        object.__setattr__(self, "target_audience", _clean_text(self.target_audience))
        object.__setattr__(self, "use_case", _clean_text(self.use_case))

    @property
    def gross_margin_mxn(self) -> int:
        return int(self.price) - int(self.cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "product_id": self.candidate_id,
            "product_name": self.product_name,
            "category": self.category,
            "market": self.market,
            "price": self.price,
            "cost": self.cost,
            "proposed_price_mxn": self.price,
            "estimated_landed_cost_mxn": self.cost,
            "gross_margin_mxn": self.gross_margin_mxn,
            "margin_pct": self.margin_pct,
            "source_type": self.source_type,
            "supplier_mode": self.supplier_mode,
            "traffic": self.traffic,
            "days": self.days,
            "marketing_angle": self.marketing_angle,
            "primary_hook": self.primary_hook,
            "target_audience": self.target_audience,
            "use_case": self.use_case,
            "demand_signals": [signal.to_dict() for signal in self.demand_signals],
            "risk_signals": [signal.to_dict() for signal in self.risk_signals],
            "differentiation_signals": [signal.to_dict() for signal in self.differentiation_signals],
            "evidence_notes": list(self.evidence_notes),
            "created_by_version": self.created_by_version,
        }

    def to_marketing_product(self) -> dict[str, Any]:
        return {
            "product_id": self.candidate_id,
            "product_name": self.product_name,
            "name": self.product_name,
            "category": self.category,
            "market": self.market,
            "price": self.price,
            "cost": self.cost,
            "proposed_price_mxn": self.price,
            "estimated_landed_cost_mxn": self.cost,
            "margin_pct": self.margin_pct,
            "target_audience": self.target_audience,
            "audience": self.target_audience,
            "use_case": self.use_case,
            "marketing_angle": self.marketing_angle,
            "primary_hook": self.primary_hook,
            "source_type": self.source_type,
            "created_by_version": self.created_by_version,
        }


def validate_candidate_contract(candidate: DiscoveryCandidate) -> tuple[str, ...]:
    errors: list[str] = []

    required_text_fields = {
        "candidate_id": candidate.candidate_id,
        "product_name": candidate.product_name,
        "category": candidate.category,
        "market": candidate.market,
        "source_type": candidate.source_type,
        "created_by_version": candidate.created_by_version,
    }

    for field_name, value in required_text_fields.items():
        if not _clean_text(value):
            errors.append(f"{field_name}:missing")

    if candidate.source_type != SYNTHETIC_SOURCE_TYPE:
        errors.append("source_type:not_synthetic")

    if candidate.created_by_version != DISCOVERY_SCHEMA_VERSION:
        errors.append("created_by_version:mismatch")

    if candidate.price <= 0:
        errors.append("price:not_positive")

    if candidate.cost < 0:
        errors.append("cost:negative")

    if candidate.gross_margin_mxn <= 0:
        errors.append("gross_margin_mxn:not_positive")

    expected_margin = calculate_margin_pct(candidate.price, candidate.cost)
    if candidate.margin_pct != expected_margin:
        errors.append(f"margin_pct:mismatch:{candidate.margin_pct}!={expected_margin}")

    if not candidate.demand_signals:
        errors.append("demand_signals:empty")

    if not candidate.risk_signals:
        errors.append("risk_signals:empty")

    if not candidate.differentiation_signals:
        errors.append("differentiation_signals:empty")

    if not candidate.evidence_notes:
        errors.append("evidence_notes:empty")

    try:
        json.dumps(candidate.to_dict(), ensure_ascii=False, sort_keys=True)
    except TypeError as exc:
        errors.append(f"json:not_serializable:{type(exc).__name__}")

    return tuple(errors)


def candidate_to_marketing_product(candidate: DiscoveryCandidate) -> dict[str, Any]:
    return candidate.to_marketing_product()


__all__ = [
    "DISCOVERY_SCHEMA_VERSION",
    "SYNTHETIC_SOURCE_TYPE",
    "DiscoveryCandidate",
    "DiscoverySignal",
    "calculate_margin_pct",
    "candidate_to_marketing_product",
    "stable_candidate_id",
    "validate_candidate_contract",
]