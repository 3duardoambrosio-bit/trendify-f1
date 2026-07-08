from __future__ import annotations

import ast
from pathlib import Path

from synapse.ui import operator_console


def _fake_artifact(run_id: str, product_id: str, product_name: str) -> dict:
    return {
        "artifact_dir": f"/tmp/{run_id}",
        "run_id": run_id,
        "manifest": {
            "run_id": run_id,
            "product_id": product_id,
            "product_name": product_name,
            "boundaries": [
                "dry_run_only",
                "operator_in_control",
                "no_live_writes",
                "no_automatic_spend",
                "no_fulfillment_automation",
                "claims_require_operator_review",
                "local_artifact_only",
                "operator_review_required",
            ],
            "ready_for_operator_review": True,
        },
        "decision": {
            "decision": "APPROVE",
            "financials": {"expected_margin": "0.30"},
        },
        "first_selling_pack": {
            "ready_for_operator_review": True,
            "warnings": ["review claims"],
            "marketing_brief": {"headline": "test"},
            "expert_pack": {"campaign": {"platform": "meta-dry-run"}},
        },
        "marketing_brief": {"headline": "test"},
        "expert_pack": {"campaign": {"platform": "meta-dry-run"}},
    }


def test_operator_console_empty_state(tmp_path: Path) -> None:
    model = operator_console.build_operator_console_model(tmp_path)

    assert model["schema_version"] == "a8-r89.operator_console.v1"
    assert model["status"] == "empty"
    assert model["row_count"] == 0
    assert model["rows"] == []
    assert model["read_only"] is True
    assert model["external_side_effects"] is False


def test_operator_console_row_has_lifecycle_stages() -> None:
    row = operator_console.build_operator_console_row(
        _fake_artifact("run-001", "sku-001", "Producto Uno")
    )

    assert row["run_id"] == "run-001"
    assert row["product_id"] == "sku-001"
    assert row["product_name"] == "Producto Uno"
    assert row["decision"] == "APPROVE"
    assert row["platform"] == "meta-dry-run"
    assert row["ready_for_operator_review"] is True
    assert row["read_only"] is True
    assert row["external_side_effects"] is False

    stages = [item["stage"] for item in row["stage_statuses"]]
    statuses = {item["stage"]: item["status"] for item in row["stage_statuses"]}

    assert stages == [
        "product",
        "evaluation",
        "decision",
        "selling_pack",
        "operator_artifact",
    ]
    assert statuses == {
        "product": "ready",
        "evaluation": "ready",
        "decision": "ready",
        "selling_pack": "ready",
        "operator_artifact": "ready",
    }


def test_operator_console_model_uses_read_model_loaders(monkeypatch, tmp_path: Path) -> None:
    artifacts = [
        _fake_artifact("run-z", "sku-z", "Zeta"),
        _fake_artifact("run-a", "sku-a", "Alpha"),
    ]

    monkeypatch.setattr(
        operator_console,
        "load_first_selling_pack_artifacts",
        lambda root, limit=8: artifacts,
    )
    monkeypatch.setattr(
        operator_console,
        "build_first_selling_pack_artifact_inventory",
        lambda root, limit=8: {"status": "ready", "artifact_count": 2},
    )

    model = operator_console.build_operator_console_model(tmp_path, limit=8)

    assert model["status"] == "ready"
    assert model["row_count"] == 2
    assert [row["run_id"] for row in model["rows"]] == ["run-a", "run-z"]
    assert model["inventory"] == {"status": "ready", "artifact_count": 2}


def test_operator_console_panel_is_presentation_ready(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        operator_console,
        "load_first_selling_pack_artifacts",
        lambda root, limit=8: [_fake_artifact("run-001", "sku-001", "Producto Uno")],
    )
    monkeypatch.setattr(
        operator_console,
        "build_first_selling_pack_artifact_inventory",
        lambda root, limit=8: {"status": "ready", "artifact_count": 1},
    )

    panel = operator_console.build_operator_console_panel(tmp_path)

    assert panel["title"] == "Operator Console"
    assert panel["status"] == "ready"
    assert panel["row_count"] == 1
    assert panel["ready_for_operator_review_count"] == 1
    assert panel["read_only"] is True
    assert panel["external_side_effects"] is False


def test_operator_console_source_has_no_external_side_effect_primitives() -> None:
    source_path = Path(operator_console.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_import_roots = {
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
    }
    forbidden_call_attrs = {
        "write_text",
        "write_bytes",
        "open",
        "unlink",
        "mkdir",
        "rmdir",
        "remove",
        "rename",
        "replace",
        "system",
        "popen",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_import_roots
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_import_roots
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_call_attrs
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_call_attrs