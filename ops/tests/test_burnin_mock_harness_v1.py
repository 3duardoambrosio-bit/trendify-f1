from __future__ import annotations

import json
from pathlib import Path

from ops.burnin_mock_harness_v1 import run_burnin_mock


def test_burnin_mock_harness_produces_deterministic_summary_and_artifacts(tmp_path: Path) -> None:
    summary = run_burnin_mock(cycles=3, output_dir=tmp_path)

    assert summary.cycles == 3
    assert summary.scenario_count_per_cycle == 4
    assert summary.dispatch_count == 12
    assert summary.status_counts["DISPATCHED"] == 6
    assert summary.status_counts["SKIPPED"] == 6
    assert summary.action_counts["test"] == 3
    assert summary.action_counts["pause"] == 3
    assert summary.action_counts["hold"] == 6
    assert summary.publisher_action_counts["create_campaign"] == 3
    assert summary.publisher_action_counts["pause_campaign"] == 3
    assert summary.publisher_action_counts["None"] == 6

    ledger_path = Path(summary.ledger_path)
    summary_path = Path(summary.summary_path)
    idem_path = Path(summary.idempotency_db_path)

    assert ledger_path.exists()
    assert summary_path.exists()
    assert idem_path.exists()
    assert summary.ledger_event_count >= 12

    event_lines = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    event_types = [json.loads(ln)["event_type"] for ln in event_lines]

    assert "meta.create_campaign.attempt" in event_types
    assert "meta.create_campaign.result" in event_types
    assert "meta.autopause.attempt" in event_types
    assert "meta.autopause.result" in event_types

    stored_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert stored_summary["cycles"] == 3
    assert stored_summary["dispatch_count"] == 12
