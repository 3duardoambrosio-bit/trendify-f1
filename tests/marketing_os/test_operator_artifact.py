from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

from synapse.marketing_os import (
    FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION,
    FirstSellingPackArtifact,
    first_selling_pack_artifact_to_dict,
    write_first_selling_pack_artifact,
)


def _product() -> dict[str, object]:
    return {
        "product_id": "KC01_GOOD_MARGIN_SAFE_CLAIM",
        "title": "Masajeador Cervical Inteligente TENS",
        "category": "wellness/fitness",
        "target_audience": "Personas que trabajan de noche frente a monitor.",
        "pain": "tension cervical despues de trabajar muchas horas frente a pantalla",
        "benefit": "reducir friccion diaria con una rutina practica de relajacion",
        "price_mxn": "799",
    }


def _decision() -> dict[str, object]:
    return {
        "final_outcome": "GO",
        "final_decision": "APPROVE",
        "confidence": Decimal("0.87"),
        "blocked_reasons": [],
        "reasons": ("margin_ok", "claims_safe", "operator_review_required"),
        "recommended_actions": ("build_brief", "review_claims", "dry_run_only"),
        "selling_price_mxn": Decimal("799"),
    }


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_write_first_selling_pack_artifact_persists_operator_files(tmp_path):
    artifact = write_first_selling_pack_artifact(
        _product(),
        _decision(),
        tmp_path,
        daily_budget_mxn=Decimal("300"),
    )

    assert isinstance(artifact, FirstSellingPackArtifact)
    assert artifact.artifact_dir.is_dir()
    assert artifact.manifest["schema_version"] == FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION
    assert artifact.manifest["artifact_type"] == "first_selling_pack_operator_artifact"

    expected_files = {
        "manifest.json",
        "scenario.json",
        "decision.json",
        "first_selling_pack.json",
        "marketing_brief.json",
        "expert_pack.json",
        "burnin_summary.json",
        "ledger.ndjson",
        "ledger_sandbox.ndjson",
        "operator_review.md",
        "creative_bundle/operator_review.md",
    }

    actual_files = {
        str(path.relative_to(artifact.artifact_dir)).replace("\\", "/")
        for path in artifact.artifact_dir.rglob("*")
        if path.is_file()
    }

    assert expected_files.issubset(actual_files)

    pack = _read_json(artifact.artifact_dir / "first_selling_pack.json")
    assert pack["ready_for_operator_review"] is True
    assert pack["expert_pack"]["campaign"]["platform"] == "meta-dry-run"
    assert pack["expert_pack"]["campaign"]["adsets"]
    assert pack["expert_pack"]["campaign"]["adsets"][0]["ads"]

    manifest = _read_json(artifact.artifact_dir / "manifest.json")
    assert "dry_run_only" in manifest["boundaries"]
    assert "operator_in_control" in manifest["boundaries"]
    assert "no_live_writes" in manifest["boundaries"]
    assert "no_automatic_spend" in manifest["boundaries"]
    assert "no_fulfillment_automation" in manifest["boundaries"]
    assert "claims_require_operator_review" in manifest["boundaries"]
    assert "local_artifact_only" in manifest["boundaries"]

    review = (artifact.artifact_dir / "operator_review.md").read_text(encoding="utf-8")
    assert "Do not publish automatically." in review
    assert "Do not spend automatically." in review


def test_first_selling_pack_artifact_is_deterministic_for_same_inputs(tmp_path):
    first = write_first_selling_pack_artifact(
        _product(),
        _decision(),
        tmp_path,
        daily_budget_mxn=Decimal("300"),
    )
    second = write_first_selling_pack_artifact(
        _product(),
        _decision(),
        tmp_path,
        daily_budget_mxn=Decimal("300"),
    )

    assert first.run_id == second.run_id
    assert first.artifact_dir == second.artifact_dir

    manifest_a = (first.artifact_dir / "manifest.json").read_text(encoding="utf-8")
    manifest_b = (second.artifact_dir / "manifest.json").read_text(encoding="utf-8")
    pack_a = (first.artifact_dir / "first_selling_pack.json").read_text(encoding="utf-8")
    pack_b = (second.artifact_dir / "first_selling_pack.json").read_text(encoding="utf-8")

    assert manifest_a == manifest_b
    assert pack_a == pack_b


def test_first_selling_pack_artifact_to_dict_is_json_ready(tmp_path):
    artifact = write_first_selling_pack_artifact(_product(), _decision(), tmp_path)
    data = first_selling_pack_artifact_to_dict(artifact)

    assert data["run_id"] == artifact.run_id
    assert data["manifest"]["schema_version"] == FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION
    assert data["files"]["first_selling_pack"].endswith("first_selling_pack.json")

    json.dumps(data, ensure_ascii=False, sort_keys=True)


def test_first_selling_pack_artifact_carries_claim_warnings(tmp_path):
    product = _product()
    product["title"] = "Crema milagro garantizada"
    product["benefit"] = "cura 100% garantizada"

    artifact = write_first_selling_pack_artifact(product, _decision(), tmp_path)
    pack = _read_json(artifact.artifact_dir / "first_selling_pack.json")

    assert pack["warnings"]
    assert any(str(warning).startswith("claims_risk:") for warning in pack["warnings"])

    decision = _read_json(artifact.artifact_dir / "decision.json")
    assert decision["warnings"] == pack["warnings"]


def test_operator_artifact_module_blocks_runtime_side_effect_surfaces():
    source = Path("synapse/marketing_os/operator_artifact.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    blocked_import_roots = {
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "boto3",
        "google",
        "facebook_business",
    }
    blocked_call_names = {
        "urlopen",
        "request",
        "post",
        "put",
        "delete",
        "patch",
        "Popen",
        "run",
        "system",
    }

    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in blocked_import_roots:
                    issues.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in blocked_import_roots:
                issues.append(node.module)
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in blocked_call_names:
                issues.append(name)

    assert issues == []