from __future__ import annotations

import json
from pathlib import Path

from synapse.ui.operator_cockpit import (
    CHECK_OK,
    CHECK_PENDING,
    _shopify_read_only_fixture_read_path_detail,
    _shopify_read_only_fixture_read_path_status,
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
        "component": "shopify_read_only_fixture_read_path",
        "status": "OK",
        "source_mode": "local_fixture_only",
        "external_io_attempted": False,
        "external_write_attempted": False,
        "live_shopify_attempted": False,
        "spend_attempted": False,
        "feature_flags": {
            "shopify_live_api": False,
            "dropi_live_orders": False,
            "meta_live_ads": False,
            "spend_real_money": False,
        },
        "fixture_read": {
            "products_loaded": True,
            "orders_loaded": True,
            "product_fixture_hit": True,
            "order_fixture_hit": True,
            "product_edges_count": 2,
            "order_edges_count": 1,
            "http_transport_called": False,
            "http_transport_call_count": 0,
        },
        "network_guard": {
            "decision": "BLOCK",
            "expected_policy_block": True,
        },
        "mutation_probe": {
            "rejected_before_io": True,
        },
        "acceptance": {
            "read_fixtures_loaded": True,
            "no_http_transport": True,
            "network_guard_policy_blocked": True,
            "mutation_rejected_before_io": True,
            "evidence_visible_to_cockpit": True,
        },
    }


def _write_summary(tmp_path: Path, payload: dict | str, *, name: str = "shopify_fixture_read_path_summary.json") -> Path:
    summary_path = tmp_path / name
    if isinstance(payload, str):
        summary_path.write_text(payload, encoding="utf-8", newline="\n")
    else:
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return summary_path


def test_shopify_fixture_read_path_slot_stays_pending_without_evidence():
    evidence = {"status": "EMPTY", "entries": []}
    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_PENDING


def test_shopify_fixture_read_path_slot_turns_ok_with_valid_a8_r76_evidence(tmp_path: Path):
    summary_path = _write_summary(tmp_path, _valid_summary())
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_OK
    assert "Valid A8-R76" in _shopify_read_only_fixture_read_path_detail(evidence)


def test_shopify_fixture_read_path_slot_stays_pending_with_blocked_summary(tmp_path: Path):
    payload = _valid_summary()
    payload["status"] = "BLOCKED"

    summary_path = _write_summary(tmp_path, payload)
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_PENDING


def test_shopify_fixture_read_path_slot_stays_pending_when_network_guard_allowed(tmp_path: Path):
    payload = _valid_summary()
    payload["network_guard"]["decision"] = "ALLOW"
    payload["network_guard"]["expected_policy_block"] = False
    payload["acceptance"]["network_guard_policy_blocked"] = False

    summary_path = _write_summary(tmp_path, payload)
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_PENDING


def test_shopify_fixture_read_path_slot_stays_pending_when_http_transport_called(tmp_path: Path):
    payload = _valid_summary()
    payload["fixture_read"]["http_transport_called"] = True
    payload["fixture_read"]["http_transport_call_count"] = 1
    payload["acceptance"]["no_http_transport"] = False

    summary_path = _write_summary(tmp_path, payload)
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_PENDING


def test_shopify_fixture_read_path_slot_stays_pending_with_empty_summary(tmp_path: Path):
    summary_path = _write_summary(tmp_path, "")
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_PENDING


def test_shopify_fixture_read_path_slot_stays_pending_with_todo_substring(tmp_path: Path):
    summary_path = _write_summary(
        tmp_path,
        "TODO: a8_r76 shopify_read_only_fixture_read_path shopify_fixture_read_path_summary.json",
    )
    evidence = _evidence_for(summary_path)

    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_PENDING


def test_shopify_fixture_read_path_slot_stays_pending_with_nonexistent_summary():
    evidence = {
        "status": "AVAILABLE",
        "entries": [
            {
                "path": "runs/a8_r76_missing/shopify_fixture_read_path_summary.json",
                "name": "shopify_fixture_read_path_summary.json",
            }
        ],
    }

    assert _shopify_read_only_fixture_read_path_status(evidence) == CHECK_PENDING
