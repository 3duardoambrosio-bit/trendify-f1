from __future__ import annotations

import importlib.util
import sys
import json
from pathlib import Path

from synapse.learning.feedback_loop import materialize_smoke_feedback_run


REPO = Path(__file__).resolve().parents[2]


def _load_a8_r70_smoke_module():
    path = REPO / "synapse" / "integration" / "a8_r70_smoke.py"
    spec = importlib.util.spec_from_file_location("_a8_r70_smoke_direct_for_r79b", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_materialize_smoke_feedback_run_writes_local_unknown_feedback(tmp_path: Path) -> None:
    smoke = _load_a8_r70_smoke_module()
    result = smoke.run_a8_r70_smoke_integration()
    before = result.to_dict()

    run_dir = tmp_path / "a8_r79b_feedback_run"
    summary = materialize_smoke_feedback_run(
        result,
        run_dir,
        generated_at="2026-06-15T00:00:00Z",
    )

    assert result.to_dict() == before
    assert summary["live_writes"] == 0
    assert summary["external_writes"] == 0
    assert summary["real_spend"] == 0

    for filename in (
        "scenario.json",
        "decision.json",
        "safety_posture.json",
        "creative_pack.json",
        "ledger_sandbox.ndjson",
        "ledger.ndjson",
        "outcome.json",
        "feedback_signal.json",
    ):
        assert (run_dir / filename).is_file(), filename

    outcome = _read_json(run_dir / "outcome.json")
    assert outcome["status"] == "UNKNOWN"
    assert outcome["observed"] is False
    assert outcome["reason_codes"] == ["MISSING_REAL_OUTCOME"]

    signal = _read_json(run_dir / "feedback_signal.json")
    assert signal.get("signal_status") == "UNKNOWN" or signal.get("status") == "UNKNOWN"
    assert "OBSERVED" not in json.dumps(signal, sort_keys=True)


def test_materialize_smoke_feedback_run_is_deterministic_for_same_result(tmp_path: Path) -> None:
    smoke = _load_a8_r70_smoke_module()
    result = smoke.run_a8_r70_smoke_integration()

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    materialize_smoke_feedback_run(result, first_dir, generated_at="2026-06-15T00:00:00Z")
    materialize_smoke_feedback_run(result, second_dir, generated_at="2026-06-15T00:00:00Z")

    assert (first_dir / "feedback_signal.json").read_text(encoding="utf-8") == (
        second_dir / "feedback_signal.json"
    ).read_text(encoding="utf-8")
    assert (first_dir / "decision.json").read_text(encoding="utf-8") == (
        second_dir / "decision.json"
    ).read_text(encoding="utf-8")

def test_materialized_smoke_feedback_waits_for_real_outcome_not_missing_prediction(tmp_path):
    import importlib.util
    import json
    import sys
    from pathlib import Path

    from synapse.learning.evidence_reader import read_run_evidence
    from synapse.learning.feedback_loop import materialize_smoke_feedback_run

    repo = Path(__file__).resolve().parents[2]
    smoke_path = repo / "synapse" / "integration" / "a8_r70_smoke.py"

    spec = importlib.util.spec_from_file_location("a8_r80_regression_smoke", smoke_path)
    assert spec is not None
    assert spec.loader is not None

    smoke = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = smoke
    spec.loader.exec_module(smoke)

    run_dir = tmp_path / "smoke_feedback_schema_fix"
    smoke_result = smoke.run_a8_r70_smoke_integration()

    materialize_smoke_feedback_run(
        smoke_result,
        run_dir,
        generated_at="1970-01-01T00:00:00Z",
    )

    scenario = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    signal = json.loads((run_dir / "feedback_signal.json").read_text(encoding="utf-8"))
    outcome = json.loads((run_dir / "outcome.json").read_text(encoding="utf-8"))
    evidence = read_run_evidence(run_dir)

    assert scenario["proposed_price_mxn"] is not None
    assert scenario["estimated_landed_cost_mxn"] is not None

    assert outcome["status"] == "UNKNOWN"
    assert outcome["observed"] is False

    assert evidence.prediction is not None

    reason_codes = [str(reason) for reason in signal["reason_codes"]]

    assert any("MISSING_REAL_OUTCOME" in reason for reason in reason_codes)
    assert not any("MISSING_PREDICTION" in reason for reason in reason_codes)
    assert not any("INVALID_PREDICTION_INPUT" in reason for reason in reason_codes)
