from decimal import Decimal

import pytest

from synapse.learning.outcome_schema import (
    FeedbackSignal,
    OutcomeSnapshot,
    OutcomeStatus,
    PredictionSnapshot,
    SignalStatus,
    decimal_from,
)


def test_decimal_from_rejects_float_for_money_and_ratios():
    with pytest.raises(ValueError):
        decimal_from(1.25, "money")


def test_prediction_snapshot_normalizes_decimal_strings():
    prediction = PredictionSnapshot(
        candidate_id="c1",
        decision_id="d1",
        expected_margin="100.50",
        expected_roi="0.25",
        risk_level="ALLOW",
        confidence="0.88",
        created_at="2026-06-14T00:00:00Z",
    )

    assert prediction.expected_margin == Decimal("100.50")
    assert prediction.expected_roi == Decimal("0.25")
    assert prediction.to_dict()["expected_margin"] == "100.50"


def test_outcome_snapshot_status_contract():
    outcome = OutcomeSnapshot(
        decision_id="d1",
        observed_revenue="300",
        observed_cost="200",
        observed_margin="100",
        observed_roi="0.5",
        source="outcome.json",
        observed_at="2026-06-14T00:00:00Z",
        status="OBSERVED",
    )

    assert outcome.status == OutcomeStatus.OBSERVED
    assert outcome.to_dict()["status"] == "OBSERVED"


def test_feedback_signal_contract_serializes_without_float():
    signal = FeedbackSignal(
        decision_id="d1",
        signal_status=SignalStatus.UNKNOWN,
        margin_delta=None,
        roi_delta=None,
        confidence_delta="0",
        recommendation="WAIT_FOR_OUTCOME",
        evidence_refs=("decision.json",),
        generated_at="2026-06-14T00:00:00Z",
        reason_codes=("MISSING_OUTCOME",),
    )

    payload = signal.to_dict()
    assert payload["confidence_delta"] == "0"
    assert payload["margin_delta"] is None
    assert payload["reason_codes"] == ["MISSING_OUTCOME"]