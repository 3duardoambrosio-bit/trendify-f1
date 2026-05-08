from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
SOURCE_CLI_PATH = TOOLS / "product_candidate_source_cli.py"
DECISION_CLI_PATH = TOOLS / "product_decision_cli.py"


def load_source_cli():
    tools_path = str(TOOLS)
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)

    spec = importlib.util.spec_from_file_location("product_candidate_source_cli", SOURCE_CLI_PATH)
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
            candidate(sku="BAD-RISK", compliance_risk_score=90.0),
            candidate(sku="MANUAL-FLAG", selected=True),
        ]
    }


def test_build_candidate_source_artifact_is_deterministic_and_auditable():
    cli = load_source_cli()
    payload = source_payload()

    first = cli.build_candidate_source_artifact(payload, source_id="research_batch_a")
    second = cli.build_candidate_source_artifact(payload, source_id="research_batch_a")

    assert first == second
    assert first["artifact_version"] == "A8-R34.product-candidate-source-cli.v1"
    assert first["artifact_type"] == "normalized_product_candidate_source"
    assert first["source_contract_version"] == "A8-R33.product-candidate-source.v1"
    assert first["source_id"] == "research_batch_a"
    assert len(first["source_sha256"]) == 64
    assert first["manual_champion_provided"] is False
    assert first["selection_mode"] == "source_normalization_only"

    report = first["source_quality_report"]
    assert report["input_rows"] == 4
    assert report["valid_candidates"] == 3
    assert report["rejected_rows"] == 1
    assert report["manual_selection_markers_blocked"] == 1

    gates = first["quality_gates"]
    assert gates["has_valid_candidates"] is True
    assert gates["manual_champion_blocked"] is True
    assert gates["ready_for_product_decision_cli"] is True


def test_source_cli_writes_artifact_and_stdout_markers(tmp_path):
    input_path = tmp_path / "source.json"
    output_path = tmp_path / "normalized_source.json"

    input_path.write_text(
        json.dumps(source_payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SOURCE_CLI_PATH),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--source-id",
            "research_batch_cli",
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
    assert "PRODUCT_CANDIDATE_SOURCE_CLI_PASS=1" in result.stdout
    assert "PRODUCT_CANDIDATE_SOURCE_VALID_CANDIDATES=3" in result.stdout
    assert "PRODUCT_CANDIDATE_SOURCE_REJECTED_ROWS=1" in result.stdout
    assert "PRODUCT_CANDIDATE_SOURCE_READY_FOR_DECISION_CLI=1" in result.stdout
    assert "PRODUCT_CANDIDATE_SOURCE_MANUAL_CHAMPION_PROVIDED=0" in result.stdout
    assert output_path.exists()

    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["source_id"] == "research_batch_cli"
    assert len(artifact["candidates"]) == 3
    assert artifact["quality_gates"]["ready_for_product_decision_cli"] is True


def test_source_cli_output_feeds_decision_cli(tmp_path):
    source_input = tmp_path / "source.json"
    normalized_output = tmp_path / "normalized_source.json"
    decision_input = tmp_path / "decision_input.json"
    decision_output = tmp_path / "decision_artifact.json"

    source_input.write_text(
        json.dumps(source_payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    source_result = subprocess.run(
        [
            sys.executable,
            str(SOURCE_CLI_PATH),
            "--input",
            str(source_input),
            "--output",
            str(normalized_output),
            "--source-id",
            "pipeline_test",
        ],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert source_result.returncode == 0, source_result.stderr

    normalized = json.loads(normalized_output.read_text(encoding="utf-8"))
    decision_input.write_text(
        json.dumps(
            {
                "backup_count": 1,
                "candidates": normalized["candidates"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    decision_result = subprocess.run(
        [
            sys.executable,
            str(DECISION_CLI_PATH),
            "--input",
            str(decision_input),
            "--output",
            str(decision_output),
        ],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert decision_result.returncode == 0, decision_result.stderr
    assert "PRODUCT_DECISION_CLI_PASS=1" in decision_result.stdout
    assert decision_output.exists()

    decision_artifact = json.loads(decision_output.read_text(encoding="utf-8"))
    assert decision_artifact["decision"]["champion"]["sku"] == "REAL-WINNER"
    assert decision_artifact["manual_selection_used"] is False


def test_source_cli_rejects_empty_source_without_output(tmp_path):
    input_path = tmp_path / "empty.json"
    output_path = tmp_path / "should_not_exist.json"

    input_path.write_text("[]", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SOURCE_CLI_PATH),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
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
    assert "PRODUCT_CANDIDATE_SOURCE_CLI_ERROR=ValueError" in result.stderr
    assert "source rows must not be empty" in result.stderr
    assert not output_path.exists()


def test_source_cli_has_no_network_random_or_dynamic_execution_markers():
    source = SOURCE_CLI_PATH.read_text(encoding="utf-8")

    forbidden_markers = [
        "requests",
        "httpx",
        "urllib",
        "socket",
        "random",
        "eval(",
        "exec(",
        "manual_override",
        "manual_pick",
        "operator_selected_champion",
    ]

    found = [marker for marker in forbidden_markers if marker in source]
    assert found == []
