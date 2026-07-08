from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
PIPELINE_CLI_PATH = TOOLS / "product_candidate_pipeline_cli.py"


def load_pipeline_cli():
    tools_path = str(TOOLS)
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)

    spec = importlib.util.spec_from_file_location("product_candidate_pipeline_cli", PIPELINE_CLI_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def candidate(**overrides):
    base = {
        "sku": "BASE-001",
        "name": "Base Candidate",
        "niche": "tech_gadgets",
        "landed_cost": 12.0,
        "sell_price": 34.0,
        "shipping_days": 7.0,
        "supplier_score": 82.0,
        "demand_score": 72.0,
        "saturation_score": 48.0,
        "content_fit_score": 76.0,
        "problem_severity_score": 64.0,
        "compliance_risk_score": 12.0,
        "return_risk_score": 22.0,
    }
    base.update(overrides)
    return base


def source_payload():
    return {
        "rows": [
            candidate(
                sku="ORDER-TRAP",
                demand_score=58.0,
                content_fit_score=57.0,
                supplier_score=72.0,
            ),
            candidate(
                sku="REAL-WINNER",
                landed_cost=10.0,
                sell_price=39.0,
                shipping_days=5.0,
                supplier_score=91.0,
                demand_score=88.0,
                saturation_score=31.0,
                content_fit_score=93.0,
                problem_severity_score=84.0,
                compliance_risk_score=8.0,
                return_risk_score=16.0,
            ),
            candidate(sku="BLOCKED-RISK", compliance_risk_score=90.0),
            candidate(sku="MANUAL-FLAG", selected=True),
        ]
    }


def test_build_pipeline_artifact_is_deterministic_and_auditable():
    cli = load_pipeline_cli()
    payload = source_payload()

    first = cli.build_product_candidate_pipeline_artifact(
        payload,
        source_id="pipeline_batch_a",
        backup_count=1,
    )
    second = cli.build_product_candidate_pipeline_artifact(
        payload,
        source_id="pipeline_batch_a",
        backup_count=1,
    )

    assert first == second

    source_artifact = first["source_artifact"]
    decision_artifact = first["decision_artifact"]
    manifest = first["pipeline_manifest"]

    assert source_artifact["artifact_version"] == "A8-R34.product-candidate-source-cli.v1"
    assert decision_artifact["artifact_version"] == "A8-R32.product-decision-cli.v1"
    assert manifest["artifact_version"] == "A8-R35.product-candidate-pipeline-cli.v1"
    assert manifest["artifact_type"] == "local_product_candidate_pipeline_manifest"

    assert manifest["source_id"] == "pipeline_batch_a"
    assert len(manifest["source_sha256"]) == 64
    assert len(manifest["decision_input_sha256"]) == 64
    assert manifest["manual_selection_used"] is False
    assert manifest["manual_champion_provided"] is False
    assert manifest["champion_sku"] == "REAL-WINNER"

    assert manifest["counts"]["source_input_rows"] == 4
    assert manifest["counts"]["source_valid_candidates"] == 3
    assert manifest["counts"]["source_rejected_rows"] == 1
    assert manifest["counts"]["decision_input_candidates"] == 3
    assert manifest["counts"]["decision_blocked_candidates"] == 1
    assert manifest["counts"]["decision_backups"] == 1

    gates = manifest["pipeline_quality_gates"]
    assert gates["source_ready_for_decision_cli"] is True
    assert gates["decision_has_champion"] is True
    assert gates["decision_champion_explainable"] is True
    assert gates["manual_selection_blocked"] is True
    assert gates["local_only_execution"] is True


def test_pipeline_cli_writes_three_artifacts_and_stdout_markers(tmp_path):
    input_path = tmp_path / "source.json"
    output_dir = tmp_path / "pipeline_out"

    input_path.write_text(
        json.dumps(source_payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PIPELINE_CLI_PATH),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--source-id",
            "pipeline_cli_test",
            "--backup-count",
            "1",
            "--pretty",
        ],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PRODUCT_CANDIDATE_PIPELINE_CLI_PASS=1" in result.stdout
    assert "PRODUCT_CANDIDATE_PIPELINE_CHAMPION_SKU=REAL-WINNER" in result.stdout
    assert "PRODUCT_CANDIDATE_PIPELINE_MANUAL_SELECTION_USED=0" in result.stdout
    assert "PRODUCT_CANDIDATE_PIPELINE_MANUAL_CHAMPION_PROVIDED=0" in result.stdout
    assert "PRODUCT_CANDIDATE_PIPELINE_SOURCE_READY=1" in result.stdout
    assert "PRODUCT_CANDIDATE_PIPELINE_DECISION_HAS_CHAMPION=1" in result.stdout

    source_artifact_path = output_dir / "normalized_candidate_source.json"
    decision_artifact_path = output_dir / "product_decision_artifact.json"
    manifest_path = output_dir / "product_candidate_pipeline_manifest.json"

    assert source_artifact_path.exists()
    assert decision_artifact_path.exists()
    assert manifest_path.exists()

    source_artifact = json.loads(source_artifact_path.read_text(encoding="utf-8"))
    decision_artifact = json.loads(decision_artifact_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert source_artifact["source_id"] == "pipeline_cli_test"
    assert decision_artifact["decision"]["champion"]["sku"] == "REAL-WINNER"
    assert manifest["champion_sku"] == "REAL-WINNER"
    assert manifest["output_files"]["source_artifact"] == "normalized_candidate_source.json"


def test_pipeline_cli_rejects_empty_source_without_outputs(tmp_path):
    input_path = tmp_path / "empty.json"
    output_dir = tmp_path / "pipeline_out"

    input_path.write_text("[]", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(PIPELINE_CLI_PATH),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 2
    assert "PRODUCT_CANDIDATE_PIPELINE_CLI_ERROR=ValueError" in result.stderr
    assert "source rows must not be empty" in result.stderr
    assert not output_dir.exists()


def test_pipeline_cli_rejects_invalid_backup_count():
    cli = load_pipeline_cli()

    try:
        cli.build_product_candidate_pipeline_artifact(
            source_payload(),
            source_id="bad_backup_count",
            backup_count=-1,
        )
    except ValueError as exc:
        assert "backup_count must be >= 0" in str(exc)
    else:
        raise AssertionError("negative backup_count must fail")


def test_pipeline_cli_has_no_network_random_or_dynamic_execution_markers():
    source = PIPELINE_CLI_PATH.read_text(encoding="utf-8").lower()

    dynamic_forbidden_markers = [
        "eval(",
        "exec(",
    ]

    word_forbidden_markers = [
        "requests",
        "httpx",
        "urllib",
        "socket",
        "random",
        "shopify",
        "facebook",
        "meta",
        "ads",
        "stripe",
        "paypal",
    ]

    dynamic_found = [marker for marker in dynamic_forbidden_markers if marker in source]
    word_found = [
        marker
        for marker in word_forbidden_markers
        if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", source)
    ]

    assert dynamic_found == []
    assert word_found == []
