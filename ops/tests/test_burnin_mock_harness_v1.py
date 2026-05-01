from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from ops.burnin_mock_harness_v1 import run_burnin_mock


def _allow_capital() -> dict[str, object]:
    return {
        "gate": "capital_shield",
        "allowed": True,
        "reason": "passed",
        "correlation_id": "burnin-test-cs-allow",
        "allocated": "10",
    }


def _block_capital() -> dict[str, object]:
    return {
        "gate": "capital_shield",
        "allowed": False,
        "reason": "insufficient_budget",
        "correlation_id": "burnin-test-cs-block",
        "allocated": "0",
    }


def _allow_safety() -> dict[str, object]:
    return {
        "gate": "safety_middleware",
        "allowed": True,
        "reason": "passed",
        "correlation_id": "burnin-test-sm-allow",
    }


def test_burnin_mock_harness_produces_deterministic_summary_and_artifacts(tmp_path: Path) -> None:
    with patch("synapse.meta.safe_client._check_capital_shield") as mock_cs:
        mock_cs.return_value = _allow_capital()

        with patch("synapse.meta.safe_client._check_safety_middleware") as mock_sm:
            mock_sm.return_value = _allow_safety()

            summary = run_burnin_mock(cycles=3, output_dir=tmp_path)

    assert summary.cycles == 3
    assert summary.scenario_count_per_cycle == 4
    assert summary.dispatch_count == 12
    assert summary.status_counts["DISPATCHED"] == 6
    assert summary.status_counts["SKIPPED"] == 6
    assert summary.status_counts.get("FAILED", 0) == 0

    assert summary.normalized_outcome_counts["DISPATCHED"] == 6
    assert summary.normalized_outcome_counts["SKIPPED"] == 6
    assert summary.normalized_outcome_counts.get("BLOCKED", 0) == 0
    assert summary.blocked_error_counts == {}

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

    events = [
        json.loads(ln)
        for ln in ledger_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    event_types = [e["event_type"] for e in events]

    assert "meta.create_campaign.attempt" in event_types
    assert "meta.create_campaign.result" in event_types
    assert "meta.autopause.attempt" in event_types
    assert "meta.autopause.result" in event_types

    stored_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert stored_summary["cycles"] == 3
    assert stored_summary["dispatch_count"] == 12
    assert stored_summary["normalized_outcome_counts"]["DISPATCHED"] == 6
    assert stored_summary["blocked_error_counts"] == {}


def test_burnin_mock_harness_surfaces_budget_blocks_separately(tmp_path: Path) -> None:
    with patch("synapse.meta.safe_client._check_capital_shield") as mock_cs:
        mock_cs.return_value = _block_capital()

        with patch("synapse.meta.safe_client._check_safety_middleware") as mock_sm:
            mock_sm.return_value = _allow_safety()

            summary = run_burnin_mock(cycles=15, output_dir=tmp_path)

    assert summary.dispatch_count == 60
    assert summary.status_counts["DISPATCHED"] == 15
    assert summary.status_counts["FAILED"] == 15
    assert summary.status_counts["SKIPPED"] == 30

    assert summary.normalized_outcome_counts["DISPATCHED"] == 15
    assert summary.normalized_outcome_counts["BLOCKED"] == 15
    assert summary.normalized_outcome_counts["SKIPPED"] == 30

    assert summary.blocked_error_counts["pre_spend_gate_blocked"] == 15

    assert summary.action_counts["test"] == 15
    assert summary.action_counts["pause"] == 15
    assert summary.action_counts["hold"] == 30

    assert summary.publisher_action_counts["create_campaign"] == 15
    assert summary.publisher_action_counts["pause_campaign"] == 15
    assert summary.publisher_action_counts["None"] == 30

    events = [
        json.loads(ln)
        for ln in Path(summary.ledger_path).read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]

    blocked = [e for e in events if e.get("event_type") == "meta.create_campaign.blocked"]
    attempt = [e for e in events if e.get("event_type") == "meta.create_campaign.attempt"]
    result = [e for e in events if e.get("event_type") == "meta.create_campaign.result"]

    assert len(blocked) == 15
    assert len(attempt) == 0
    assert len(result) == 0

    payload = blocked[0]["payload"]
    assert payload["error_code"] == "pre_spend_gate_blocked"
    assert payload["blocked_by"] == ["capital_shield"]
    assert payload["capital_shield"]["reason"] == "insufficient_budget"
    assert payload["safety_middleware"]["reason"] == "passed"

    stored_summary = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))
    assert stored_summary["status_counts"]["FAILED"] == 15
    assert stored_summary["normalized_outcome_counts"]["BLOCKED"] == 15
    assert stored_summary["blocked_error_counts"]["pre_spend_gate_blocked"] == 15
