from __future__ import annotations

from decimal import Decimal

from synapse.marketing_os import write_first_selling_pack_artifact
from synapse.ui import operator_cockpit


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


def test_cockpit_builds_first_selling_pack_artifact_panel(tmp_path):
    artifact = write_first_selling_pack_artifact(_product(), _decision(), tmp_path)

    panel = operator_cockpit.build_first_selling_pack_artifact_panel(tmp_path)

    assert panel["schema_version"] == "a8-r88.first_selling_pack_artifact_panel.v1"
    assert panel["status"] == "ready"
    assert panel["artifact_count"] == 1
    assert panel["visible_artifact_count"] == 1
    assert panel["latest_artifact_dir"] == str(artifact.artifact_dir)
    assert panel["read_only"] is True
    assert panel["external_side_effects"] is False
    assert panel["artifacts"][0]["platform"] == "meta-dry-run"
    assert panel["artifacts"][0]["ad_count"] == 3
    assert "operator_review_required" in panel["boundaries"]


def test_cockpit_first_selling_pack_artifact_panel_handles_empty_root(tmp_path):
    panel = operator_cockpit.build_first_selling_pack_artifact_panel(tmp_path)

    assert panel["status"] == "ready"
    assert panel["artifact_count"] == 0
    assert panel["visible_artifact_count"] == 0
    assert panel["latest_artifact_dir"] == "N/A"
    assert panel["artifacts"] == []
    assert panel["read_only"] is True
    assert panel["external_side_effects"] is False