from decimal import Decimal

from synapse.learning.feedback_signal import derive_feedback_signal
from synapse.learning.outcome_schema import OutcomeSnapshot, PredictionSnapshot, SignalStatus


def _prediction():
    return PredictionSnapshot(
        candidate_id="c1",
        decision_id="d1",
        expected_margin="100",
        expected_roi="0.50",
        risk_level="ALLOW",
        confidence="0.80",
        created_at="2026-06-14T00:00:00Z",
    )


def test_missing_outcome_degrades_to_unknown():
    signal = derive_feedback_signal(
        prediction=_prediction(),
        outcome=None,
        evidence_refs=("scenario.json", "decision.json"),
        generated_at="2026-06-14T00:00:00Z",
    )

    assert signal.signal_status == SignalStatus.UNKNOWN
    assert signal.margin_delta is None
    assert signal.roi_delta is None
    assert signal.recommendation == "WAIT_FOR_OUTCOME"
    assert "MISSING_OUTCOME" in signal.reason_codes


def test_observed_outcome_calculates_margin_and_roi_delta():
    outcome = OutcomeSnapshot(
        decision_id="d1",
        observed_revenue="360",
        observed_cost="200",
        observed_margin="160",
        observed_roi="0.80",
        source="outcome.json",
        observed_at="2026-06-14T00:00:00Z",
        status="OBSERVED",
    )

    signal = derive_feedback_signal(
        prediction=_prediction(),
        outcome=outcome,
        evidence_refs=("decision.json", "outcome.json"),
        generated_at="2026-06-14T00:00:00Z",
    )

    assert signal.signal_status == SignalStatus.OBSERVED
    assert signal.margin_delta == Decimal("60")
    assert signal.roi_delta == Decimal("0.30")
    assert signal.confidence_delta == Decimal("0.05")
    assert signal.recommendation == "REINFORCE"


def test_mismatched_decision_id_degrades_to_invalid():
    outcome = OutcomeSnapshot(
        decision_id="other",
        observed_revenue="360",
        observed_cost="200",
        observed_margin="160",
        observed_roi="0.80",
        source="outcome.json",
        observed_at="2026-06-14T00:00:00Z",
        status="OBSERVED",
    )

    signal = derive_feedback_signal(
        prediction=_prediction(),
        outcome=outcome,
        evidence_refs=("decision.json", "outcome.json"),
        generated_at="2026-06-14T00:00:00Z",
    )

    assert signal.signal_status == SignalStatus.INVALID
    assert signal.recommendation == "REJECT_OUTCOME"
    assert "DECISION_ID_MISMATCH" in signal.reason_codes


def test_evidence_refs_are_deduped_with_stable_order():
    signal = derive_feedback_signal(
        prediction=_prediction(),
        outcome=None,
        evidence_refs=("b.json", "a.json", "b.json"),
        generated_at="2026-06-14T00:00:00Z",
    )

    assert signal.evidence_refs == ("b.json", "a.json")