from __future__ import annotations

from synapse.ui import operator_cockpit as cockpit


def test_build_operator_console_cockpit_panel_delegates_to_operator_console_model(monkeypatch, tmp_path):
    calls = {}

    def fake_build_operator_console_panel(root, *, limit=8):
        calls["root"] = root
        calls["limit"] = limit
        return {
            "schema_version": "a8-r89.operator_console.v1",
            "title": "Operator Console",
            "status": "ready",
            "row_count": 1,
            "ready_for_operator_review_count": 1,
            "stage_order": [
                "product",
                "evaluation",
                "decision",
                "selling_pack",
                "operator_artifact",
            ],
            "rows": [
                {
                    "run_id": "run-001",
                    "product_id": "sku-001",
                    "ready_for_operator_review": True,
                    "read_only": True,
                    "external_side_effects": False,
                }
            ],
            "read_only": True,
            "external_side_effects": False,
        }

    monkeypatch.setattr(
        cockpit,
        "build_operator_console_panel",
        fake_build_operator_console_panel,
    )

    panel = cockpit.build_operator_console_cockpit_panel(tmp_path, limit=3)

    assert calls == {"root": tmp_path, "limit": 3}
    assert panel["schema_version"] == "a8-r89.operator_cockpit.operator_console.v1"
    assert panel["title"] == "Operator Console"
    assert panel["status"] == "ready"
    assert panel["row_count"] == 1
    assert panel["ready_for_operator_review_count"] == 1
    assert panel["read_only"] is True
    assert panel["external_side_effects"] is False
    assert panel["live_connectors"] is False
    assert panel["live_writes"] is False
    assert panel["spend_enabled"] is False
    assert panel["fulfillment_automation"] is False
    assert panel["operator_review_required"] is True
    assert panel["source_model"]["schema_version"] == "a8-r89.operator_console.v1"


def test_build_operator_console_cockpit_panel_empty_state_is_read_only(tmp_path):
    panel = cockpit.build_operator_console_cockpit_panel(tmp_path, limit=8)

    assert panel["schema_version"] == "a8-r89.operator_cockpit.operator_console.v1"
    assert panel["title"] == "Operator Console"
    assert panel["status"] == "empty"
    assert panel["row_count"] == 0
    assert panel["rows"] == []
    assert panel["read_only"] is True
    assert panel["external_side_effects"] is False
    assert panel["live_connectors"] is False
    assert panel["live_writes"] is False
    assert panel["spend_enabled"] is False
    assert panel["fulfillment_automation"] is False
    assert panel["operator_review_required"] is True
