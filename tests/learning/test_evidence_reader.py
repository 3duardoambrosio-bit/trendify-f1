import json

from synapse.learning.evidence_reader import (
    build_feedback_signal_for_run_dir,
    read_run_evidence,
    write_feedback_signal,
)
from synapse.learning.outcome_schema import SignalStatus


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def test_read_run_evidence_builds_prediction_and_unknown_without_outcome(tmp_path):
    _write_json(
        tmp_path / "scenario.json",
        {
            "scenario_id": "s1",
            "product_name": "Producto Test",
            "proposed_price_mxn": "300",
            "estimated_landed_cost_mxn": "200",
        },
    )
    _write_json(
        tmp_path / "decision.json",
        {
            "decision_id": "d1",
            "final_outcome": "ALLOW",
            "score": "80",
        },
    )

    result = read_run_evidence(tmp_path)

    assert result.prediction is not None
    assert result.prediction.expected_margin == 100
    assert str(result.prediction.expected_roi) == "0.5"
    assert result.outcome is None
    assert "MISSING_OUTCOME_JSON" in result.reason_codes

    signal = build_feedback_signal_for_run_dir(tmp_path, "2026-06-14T00:00:00Z")
    assert signal.signal_status == SignalStatus.UNKNOWN
    assert signal.recommendation == "WAIT_FOR_OUTCOME"


def test_read_run_evidence_with_observed_outcome_produces_observed_signal(tmp_path):
    _write_json(
        tmp_path / "scenario.json",
        {
            "scenario_id": "s1",
            "product_name": "Producto Test",
            "proposed_price_mxn": "300",
            "estimated_landed_cost_mxn": "200",
        },
    )
    _write_json(
        tmp_path / "decision.json",
        {
            "decision_id": "d1",
            "final_outcome": "ALLOW",
            "score": "80",
        },
    )
    _write_json(
        tmp_path / "outcome.json",
        {
            "decision_id": "d1",
            "observed_revenue": "360",
            "observed_cost": "200",
            "observed_at": "2026-06-14T00:00:00Z",
        },
    )

    signal = build_feedback_signal_for_run_dir(tmp_path, "2026-06-14T01:00:00Z")

    assert signal.signal_status == SignalStatus.OBSERVED
    assert str(signal.margin_delta) == "60"
    assert str(signal.roi_delta) == "0.3"


def test_malformed_money_degrades_without_source_mutation(tmp_path):
    scenario = tmp_path / "scenario.json"
    decision = tmp_path / "decision.json"

    _write_json(
        scenario,
        {
            "scenario_id": "s1",
            "product_name": "Producto Test",
            "proposed_price_mxn": "NOPE",
            "estimated_landed_cost_mxn": "200",
        },
    )
    _write_json(decision, {"decision_id": "d1", "final_outcome": "ALLOW", "score": "80"})

    before = scenario.read_text(encoding="utf-8")

    result = read_run_evidence(tmp_path)

    assert result.prediction is None
    assert any(code.startswith("INVALID_PREDICTION_INPUT") for code in result.reason_codes)
    assert scenario.read_text(encoding="utf-8") == before


def test_write_feedback_signal_writes_derived_evidence_only_to_requested_path(tmp_path):
    _write_json(
        tmp_path / "scenario.json",
        {
            "scenario_id": "s1",
            "product_name": "Producto Test",
            "proposed_price_mxn": "300",
            "estimated_landed_cost_mxn": "200",
        },
    )
    _write_json(tmp_path / "decision.json", {"decision_id": "d1", "final_outcome": "ALLOW", "score": "80"})

    signal = build_feedback_signal_for_run_dir(tmp_path, "2026-06-14T00:00:00Z")
    output = write_feedback_signal(signal, tmp_path / "derived" / "feedback_signal.json")

    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["signal_status"] == "UNKNOWN"
    assert (tmp_path / "scenario.json").exists()
    assert (tmp_path / "decision.json").exists()