"""A8-R79A local outcome and feedback contracts.

This module is intentionally deterministic, dependency-free, and local-only.
It does not read network state, mutate source artifacts, or perform live writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable


class OutcomeStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


class SignalStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


def decimal_from(value: Any, field_name: str) -> Decimal:
    """Parse a strict Decimal value.

    Floats are rejected because SYNAPSE money and ratios must not depend on
    binary floating-point representation.
    """

    if isinstance(value, Decimal):
        return value

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be Decimal-compatible, got bool")

    if isinstance(value, float):
        raise ValueError(f"{field_name} must not be float")

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must not be empty")
        try:
            return Decimal(stripped)
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} is not a valid Decimal: {value!r}") from exc

    raise ValueError(f"{field_name} must be Decimal-compatible, got {type(value).__name__}")


def optional_decimal_from(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return decimal_from(value, field_name)


def _required_text(value: Any, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _text_tuple(values: Iterable[Any] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            result.append(text)
    return tuple(result)


def _coerce_outcome_status(value: OutcomeStatus | str) -> OutcomeStatus:
    if isinstance(value, OutcomeStatus):
        return value
    try:
        return OutcomeStatus(str(value).strip().upper())
    except ValueError as exc:
        raise ValueError(f"unknown outcome status: {value!r}") from exc


def _coerce_signal_status(value: SignalStatus | str) -> SignalStatus:
    if isinstance(value, SignalStatus):
        return value
    try:
        return SignalStatus(str(value).strip().upper())
    except ValueError as exc:
        raise ValueError(f"unknown signal status: {value!r}") from exc


@dataclass(frozen=True)
class PredictionSnapshot:
    candidate_id: str
    decision_id: str
    expected_margin: Decimal
    expected_roi: Decimal
    risk_level: str
    confidence: Decimal
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _required_text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "decision_id", _required_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "expected_margin", decimal_from(self.expected_margin, "expected_margin"))
        object.__setattr__(self, "expected_roi", decimal_from(self.expected_roi, "expected_roi"))
        object.__setattr__(self, "risk_level", _required_text(self.risk_level, "risk_level"))
        object.__setattr__(self, "confidence", decimal_from(self.confidence, "confidence"))
        object.__setattr__(self, "created_at", _required_text(self.created_at, "created_at"))

    def to_dict(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "decision_id": self.decision_id,
            "expected_margin": str(self.expected_margin),
            "expected_roi": str(self.expected_roi),
            "risk_level": self.risk_level,
            "confidence": str(self.confidence),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class OutcomeSnapshot:
    decision_id: str
    observed_revenue: Decimal | None
    observed_cost: Decimal | None
    observed_margin: Decimal | None
    observed_roi: Decimal | None
    source: str
    observed_at: str
    status: OutcomeStatus = OutcomeStatus.UNKNOWN
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _required_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "observed_revenue", optional_decimal_from(self.observed_revenue, "observed_revenue"))
        object.__setattr__(self, "observed_cost", optional_decimal_from(self.observed_cost, "observed_cost"))
        object.__setattr__(self, "observed_margin", optional_decimal_from(self.observed_margin, "observed_margin"))
        object.__setattr__(self, "observed_roi", optional_decimal_from(self.observed_roi, "observed_roi"))
        object.__setattr__(self, "source", _required_text(self.source, "source"))
        object.__setattr__(self, "observed_at", _required_text(self.observed_at, "observed_at"))
        object.__setattr__(self, "status", _coerce_outcome_status(self.status))
        object.__setattr__(self, "reason_codes", _text_tuple(self.reason_codes))

    def to_dict(self) -> dict[str, str | list[str] | None]:
        return {
            "decision_id": self.decision_id,
            "observed_revenue": None if self.observed_revenue is None else str(self.observed_revenue),
            "observed_cost": None if self.observed_cost is None else str(self.observed_cost),
            "observed_margin": None if self.observed_margin is None else str(self.observed_margin),
            "observed_roi": None if self.observed_roi is None else str(self.observed_roi),
            "source": self.source,
            "observed_at": self.observed_at,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class FeedbackSignal:
    decision_id: str
    signal_status: SignalStatus
    margin_delta: Decimal | None
    roi_delta: Decimal | None
    confidence_delta: Decimal
    recommendation: str
    evidence_refs: tuple[str, ...]
    generated_at: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _required_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "signal_status", _coerce_signal_status(self.signal_status))
        object.__setattr__(self, "margin_delta", optional_decimal_from(self.margin_delta, "margin_delta"))
        object.__setattr__(self, "roi_delta", optional_decimal_from(self.roi_delta, "roi_delta"))
        object.__setattr__(self, "confidence_delta", decimal_from(self.confidence_delta, "confidence_delta"))
        object.__setattr__(self, "recommendation", _required_text(self.recommendation, "recommendation"))
        object.__setattr__(self, "evidence_refs", _text_tuple(self.evidence_refs))
        object.__setattr__(self, "generated_at", _required_text(self.generated_at, "generated_at"))
        object.__setattr__(self, "reason_codes", _text_tuple(self.reason_codes))

    def to_dict(self) -> dict[str, str | list[str] | None]:
        return {
            "decision_id": self.decision_id,
            "signal_status": self.signal_status.value,
            "margin_delta": None if self.margin_delta is None else str(self.margin_delta),
            "roi_delta": None if self.roi_delta is None else str(self.roi_delta),
            "confidence_delta": str(self.confidence_delta),
            "recommendation": self.recommendation,
            "evidence_refs": list(self.evidence_refs),
            "generated_at": self.generated_at,
            "reason_codes": list(self.reason_codes),
        }