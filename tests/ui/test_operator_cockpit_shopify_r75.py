from __future__ import annotations

from synapse.ui.operator_cockpit import (
    CHECK_OK,
    CHECK_PENDING,
    _shopify_read_only_dry_run_detail,
    _shopify_read_only_dry_run_status,
)


def test_shopify_read_only_dry_run_slot_stays_pending_without_evidence():
    evidence = {"status": "AVAILABLE", "entries": []}
    assert _shopify_read_only_dry_run_status(evidence) == CHECK_PENDING


def test_shopify_read_only_dry_run_slot_turns_ok_with_a8_r75_evidence():
    evidence = {
        "status": "AVAILABLE",
        "entries": [
            {
                "path": "runs/a8_r75_shopify_readonly_dryrun_20260611/shopify_read_only_dry_run_summary.json",
                "name": "shopify_read_only_dry_run_summary.json",
            }
        ],
    }

    assert _shopify_read_only_dry_run_status(evidence) == CHECK_OK
    assert "A8-R75" in _shopify_read_only_dry_run_detail(evidence)
