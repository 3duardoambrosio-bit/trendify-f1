from __future__ import annotations

import json
from pathlib import Path

from synapse.ui import read_model


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _make_complete_run(root: Path) -> Path:
    run_dir = root / "run_feedback"
    run_dir.mkdir()

    _write_json(run_dir / "scenario.json", {"product_name": "Producto feedback"})
    _write_json(
        run_dir / "decision.json",
        {
            "score": "0.75",
            "threshold": "0.60",
            "permission_gate": "READY_FOR_SANDBOX_BRIEF",
            "final_outcome": "READY_FOR_SANDBOX_BRIEF",
        },
    )
    _write_json(
        run_dir / "safety_posture.json",
        {"runtime_mode": "sandbox", "live_reads": 0, "live_writes": 0},
    )
    _write_json(
        run_dir / "creative_pack.json",
        {"hooks": ["Hook feedback"], "angles": ["observability"]},
    )
    (run_dir / "ledger_sandbox.ndjson").write_text(
        json.dumps({"event": "sandbox"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "ledger.ndjson").write_text(
        json.dumps({"event": "ledger"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_dir


def test_load_product_run_exposes_feedback_signal_when_present(tmp_path: Path) -> None:
    run_dir = _make_complete_run(tmp_path)
    _write_json(
        run_dir / "feedback_signal.json",
        {
            "signal_status": "UNKNOWN",
            "recommendation": "WAIT_FOR_OUTCOME",
            "reason_codes": ["MISSING_REAL_OUTCOME"],
        },
    )

    run = read_model.load_product_run(run_dir)

    assert run.feedback_status == "UNKNOWN"
    assert run.feedback_recommendation == "WAIT_FOR_OUTCOME"
    assert run.feedback_reason_codes == ["MISSING_REAL_OUTCOME"]


def test_load_product_run_feedback_defaults_to_unknown_when_absent(tmp_path: Path) -> None:
    run_dir = _make_complete_run(tmp_path)

    run = read_model.load_product_run(run_dir)

    assert run.feedback_status == "UNKNOWN"
    assert run.feedback_recommendation == "UNKNOWN"
    assert run.feedback_reason_codes == []

