from __future__ import annotations

from decimal import Decimal

from synapse.marketing_os import write_first_selling_pack_artifact
from synapse.ui import read_model


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


def test_read_model_discovers_first_selling_pack_artifact(tmp_path):
    artifact = write_first_selling_pack_artifact(
        _product(),
        _decision(),
        tmp_path,
        daily_budget_mxn=Decimal("300"),
    )

    discovered = read_model.discover_first_selling_pack_artifact_dirs(tmp_path)

    assert discovered == [artifact.artifact_dir]


def test_read_model_loads_first_selling_pack_artifact(tmp_path):
    artifact = write_first_selling_pack_artifact(_product(), _decision(), tmp_path)

    loaded = read_model.load_first_selling_pack_artifact(artifact.artifact_dir)

    assert loaded["schema_version"] == "a8-r88.first_selling_pack_artifact.v1"
    assert loaded["artifact_type"] == "first_selling_pack_operator_artifact"
    assert loaded["platform"] == "meta-dry-run"
    assert loaded["ready_for_operator_review"] is True
    assert loaded["adset_count"] == 1
    assert loaded["ad_count"] == 3
    assert "no_live_writes" in loaded["boundaries"]
    assert "no_automatic_spend" in loaded["boundaries"]
    assert "local_artifact_only" in loaded["boundaries"]


def test_read_model_builds_first_selling_pack_artifact_inventory(tmp_path):
    first = write_first_selling_pack_artifact(
        _product(),
        _decision(),
        tmp_path,
        run_id="a8_r88_first",
    )
    second = write_first_selling_pack_artifact(
        _product(),
        _decision(),
        tmp_path,
        run_id="a8_r88_second",
    )

    inventory = read_model.build_first_selling_pack_artifact_inventory(tmp_path)

    assert inventory["artifact_count"] == 2
    assert inventory["visible_artifact_count"] == 2
    assert inventory["latest_artifact_dir"] == str(second.artifact_dir)
    assert inventory["latest_run_id"] == second.run_id
    assert inventory["read_only"] is True
    assert inventory["external_side_effects"] is False
    assert str(first.artifact_dir) in [item["path"] for item in inventory["artifacts"]]


def test_read_model_first_selling_pack_artifact_rejects_incomplete_dir(tmp_path):
    incomplete = tmp_path / "bad_artifact"
    incomplete.mkdir()
    (incomplete / "manifest.json").write_text("{}", encoding="utf-8")

    assert read_model.is_first_selling_pack_artifact_dir(incomplete) is False
    assert read_model.discover_first_selling_pack_artifact_dirs(tmp_path) == []