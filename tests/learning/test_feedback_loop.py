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

