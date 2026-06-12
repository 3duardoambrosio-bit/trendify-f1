from __future__ import annotations

import json
from pathlib import Path

from synapse.ui.operator_cockpit import (
    CHECK_OK,
    CHECK_PENDING,
    _shopify_read_only_dry_run_detail,
    _shopify_read_only_dry_run_status,
)


def _evidence_for(path: Path) -> dict:
    return {
        "status": "AVAILABLE",
        "entries": [
            {
                "path": str(path),
                "name": path.name,
            }
        ],
    }


def _valid_summary() -> dict:
    return {
        "component": "shopify_read_only_dry_run",
        "status": "OK",
        "external_io_attempted": False,
        "external_write_attempted": False,
        "live_shopify_attempted": False,
        "spend_attempted": False,
        "mutation_probe": {
            "rejected_before_io": True,
        },
        "network_guard": {
            "decision": "BLOCK",
            "expected_policy_block": True,
        },
    }


def _write_summary(tmp_path: Path, payload: dict | str) -> Path:
    summary_path = tmp_path / "shopify_read_only_dry_run_summary.json"

    if isinstance(payload, str):
        summary_path.write_text(payload, encoding="utf-8", newline="\n")
    else:
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    return summary_path


def test_shopify_read_only_dry_run_slot_stays_pending_without_evidence():
    evidence = {"status": "AVAILABLE", "entries": []}
    assert _shopify_read_only_dry_run_status(evidence) == CHECK_PENDING


def test_shopify_read_only_dry_run_slot_turns_ok_with_valid_a8_r75_evidence(tmp_path: Path):
    summary_path = _write_summary(tmp_path, _valid_summary())
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_dry_run_status(evidence) == CHECK_OK
    assert "Valid A8-R75" in _shopify_read_only_dry_run_detail(evidence)


def test_shopify_read_only_dry_run_slot_stays_pending_with_blocked_summary(tmp_path: Path):
    payload = _valid_summary()
    payload["status"] = "BLOCKED"

    summary_path = _write_summary(tmp_path, payload)
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_dry_run_status(evidence) == CHECK_PENDING


def test_shopify_read_only_dry_run_slot_stays_pending_when_network_guard_allowed(tmp_path: Path):
    payload = _valid_summary()
    payload["network_guard"]["decision"] = "ALLOW"
    payload["network_guard"]["expected_policy_block"] = False

    summary_path = _write_summary(tmp_path, payload)
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_dry_run_status(evidence) == CHECK_PENDING


def test_shopify_read_only_dry_run_slot_stays_pending_with_empty_summary(tmp_path: Path):
    summary_path = _write_summary(tmp_path, "")
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_dry_run_status(evidence) == CHECK_PENDING


def test_shopify_read_only_dry_run_slot_stays_pending_with_todo_substring(tmp_path: Path):
    summary_path = _write_summary(
        tmp_path,
        "TODO: a8_r75_shopify_readonly_dryrun shopify_read_only_dry_run_summary.json",
    )
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_dry_run_status(evidence) == CHECK_PENDING


def test_shopify_read_only_dry_run_slot_stays_pending_with_nonexistent_summary():
    evidence = {
        "status": "AVAILABLE",
        "entries": [
            {
                "path": "runs/a8_r75_shopify_readonly_dryrun_missing/shopify_read_only_dry_run_summary.json",
                "name": "shopify_read_only_dry_run_summary.json",
            }
        ],
    }

    assert _shopify_read_only_dry_run_status(evidence) == CHECK_PENDING
