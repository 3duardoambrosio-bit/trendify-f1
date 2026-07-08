"""Deterministic feedback signal derivation for A8-R79A."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from synapse.learning.outcome_schema import (
    FeedbackSignal,
    OutcomeSnapshot,
    OutcomeStatus,
    PredictionSnapshot,
    SignalStatus,
)

_ZERO = Decimal("0")
_CONFIDENCE_STEP = Decimal("0.05")


def _stable_refs(values: Iterable[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _recommendation(margin_delta: Decimal, roi_delta: Decimal) -> tuple[str, Decimal]:
    if margin_delta >= _ZERO and roi_delta >= _ZERO:
        return "REINFORCE", _CONFIDENCE_STEP
    if margin_delta < _ZERO and roi_delta < _ZERO:
        return "REDUCE_CONFIDENCE", -_CONFIDENCE_STEP
    return "REVIEW", _ZERO


def derive_feedback_signal(
    prediction: PredictionSnapshot | None,
    outcome: OutcomeSnapshot | None,
    evidence_refs: Iterable[str] | None,
    generated_at: str,
) -> FeedbackSignal:
    """Derive a local deterministic signal.

    Missing outcome degrades to UNKNOWN. Malformed or mismatched critical data
    degrades to INVALID. No network or external write is attempted here.
    """

    refs = _stable_refs(evidence_refs)

    if prediction is None:
        return FeedbackSignal(
            decision_id="UNKNOWN",
            signal_status=SignalStatus.UNKNOWN,
            margin_delta=None,
            roi_delta=None,
            confidence_delta=_ZERO,
            recommendation="WAIT_FOR_PREDICTION",
            evidence_refs=refs,
            generated_at=generated_at,
            reason_codes=("MISSING_PREDICTION",),
        )

    if outcome is None:
        return FeedbackSignal(
            decision_id=prediction.decision_id,
            signal_status=SignalStatus.UNKNOWN,
            margin_delta=None,
            roi_delta=None,
            confidence_delta=_ZERO,
            recommendation="WAIT_FOR_OUTCOME",
            evidence_refs=refs,
            generated_at=generated_at,
            reason_codes=("MISSING_OUTCOME",),
        )

    if outcome.decision_id != prediction.decision_id:
        return FeedbackSignal(
            decision_id=prediction.decision_id,
            signal_status=SignalStatus.INVALID,
            margin_delta=None,
            roi_delta=None,
            confidence_delta=_ZERO,
            recommendation="REJECT_OUTCOME",
            evidence_refs=refs,
            generated_at=generated_at,
            reason_codes=("DECISION_ID_MISMATCH",),
        )

    if outcome.status == OutcomeStatus.INVALID:
        return FeedbackSignal(
            decision_id=prediction.decision_id,
            signal_status=SignalStatus.INVALID,
            margin_delta=None,
            roi_delta=None,
            confidence_delta=_ZERO,
            recommendation="REJECT_OUTCOME",
            evidence_refs=refs,
            generated_at=generated_at,
            reason_codes=outcome.reason_codes or ("INVALID_OUTCOME",),
        )

    if outcome.status in (OutcomeStatus.UNKNOWN, OutcomeStatus.PARTIAL):
        status = SignalStatus.PARTIAL if outcome.status == OutcomeStatus.PARTIAL else SignalStatus.UNKNOWN
        return FeedbackSignal(
            decision_id=prediction.decision_id,
            signal_status=status,
            margin_delta=None,
            roi_delta=None,
            confidence_delta=_ZERO,
            recommendation="WAIT_FOR_COMPLETE_OUTCOME",
            evidence_refs=refs,
            generated_at=generated_at,
            reason_codes=outcome.reason_codes or (f"OUTCOME_{outcome.status.value}",),
        )

    if outcome.observed_margin is None or outcome.observed_roi is None:
        return FeedbackSignal(
            decision_id=prediction.decision_id,
            signal_status=SignalStatus.INVALID,
            margin_delta=None,
            roi_delta=None,
            confidence_delta=_ZERO,
            recommendation="REJECT_OUTCOME",
            evidence_refs=refs,
            generated_at=generated_at,
            reason_codes=("MISSING_OBSERVED_MARGIN_OR_ROI",),
        )

    margin_delta = outcome.observed_margin - prediction.expected_margin
    roi_delta = outcome.observed_roi - prediction.expected_roi
    recommendation, confidence_delta = _recommendation(margin_delta, roi_delta)

    return FeedbackSignal(
        decision_id=prediction.decision_id,
        signal_status=SignalStatus.OBSERVED,
        margin_delta=margin_delta,
        roi_delta=roi_delta,
        confidence_delta=confidence_delta,
        recommendation=recommendation,
        evidence_refs=refs,
        generated_at=generated_at,
        reason_codes=("OBSERVED_OUTCOME_COMPARED",),
    )