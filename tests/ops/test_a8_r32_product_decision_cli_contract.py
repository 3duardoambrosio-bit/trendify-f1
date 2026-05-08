from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CLI_PATH = REPO / "tools" / "product_decision_cli.py"


def load_cli():
    tools_path = str(REPO / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)

    spec = importlib.util.spec_from_file_location("product_decision_cli", CLI_PATH)
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


def payload():
    return {
        "backup_count": 2,
        "constraints": {
            "min_gross_margin_pct": 35.0,
            "max_shipping_days": 12.0,
        },
        "candidates": [
            candidate(
                sku="ORDER-TRAP",
                name="First Item Should Not Win",
                demand_score=56.0,
                content_fit_score=58.0,
                supplier_score=73.0,
            ),
            candidate(
                sku="WINNER-001",
                name="Portable Airflow Gadget",
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
            candidate(
                sku="BACKUP-001",
                name="Smart Desk Light",
                demand_score=78.0,
                content_fit_score=84.0,
                problem_severity_score=72.0,
                saturation_score=42.0,
            ),
            candidate(
                sku="BLOCKED-RISK",
                name="Risky Candidate",
                compliance_risk_score=65.0,
                return_risk_score=70.0,
            ),
        ],
    }


def canonical_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def test_build_product_decision_artifact_is_deterministic_and_auditable():
    cli = load_cli()
    data = payload()

    first = cli.build_product_decision_artifact(data)
    second = cli.build_product_decision_artifact(data)

    assert first == second
    assert first["artifact_version"] == "A8-R32.product-decision-cli.v1"
    assert first["artifact_type"] == "product_decision_packet"
    assert first["manual_selection_used"] is False
    assert first["selection_mode"] == "system_scored"
    assert first["operator_role"] == "strategy_constraints_and_gate_approval"

    expected_hash = hashlib.sha256(
        canonical_json(
            {
                "candidates": data["candidates"],
                "constraints": data["constraints"],
                "weights": None,
                "backup_count": 2,
            }
        ).encode("utf-8")
    ).hexdigest().upper()

    assert first["input_sha256"] == expected_hash
    assert first["quality_gates"]["has_candidates"] is True
    assert first["quality_gates"]["has_champion"] is True
    assert first["quality_gates"]["champion_explainable"] is True
    assert first["quality_gates"]["manual_selection_blocked_as_primary_flow"] is True
    assert first["quality_gates"]["deterministic_input_hash_present"] is True

    decision = first["decision"]
    assert decision["champion"]["sku"] == "WINNER-001"
    assert decision["counts"]["input"] == 4
    assert decision["counts"]["passed"] == 3
    assert decision["counts"]["blocked"] == 1
    assert decision["counts"]["backups"] == 2
    assert decision["rejected_candidates"][0]["sku"] == "BLOCKED-RISK"


def test_cli_writes_json_artifact_and_stdout_markers(tmp_path):
    input_path = tmp_path / "candidates.json"
    output_path = tmp_path / "decision_artifact.json"

    input_path.write_text(
        json.dumps(payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
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
    assert "PRODUCT_DECISION_CLI_PASS=1" in result.stdout
    assert "PRODUCT_DECISION_MANUAL_SELECTION_USED=0" in result.stdout
    assert "PRODUCT_DECISION_HAS_CHAMPION=1" in result.stdout
    assert output_path.exists()

    artifact = json.loads(output_path.read_text(encoding="utf-8"))

    assert artifact["decision"]["champion"]["sku"] == "WINNER-001"
    assert artifact["manual_selection_used"] is False
    assert artifact["quality_gates"]["has_champion"] is True
    assert artifact["quality_gates"]["manual_selection_blocked_as_primary_flow"] is True
    assert len(artifact["input_sha256"]) == 64


def test_cli_accepts_raw_candidate_list(tmp_path):
    input_path = tmp_path / "raw_candidates.json"
    output_path = tmp_path / "decision_artifact.json"

    input_path.write_text(
        json.dumps([candidate(sku="ONLY-VALID")], ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
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

    assert result.returncode == 0, result.stderr
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["decision"]["champion"]["sku"] == "ONLY-VALID"


def test_cli_rejects_invalid_payload_without_output(tmp_path):
    input_path = tmp_path / "bad.json"
    output_path = tmp_path / "should_not_exist.json"

    input_path.write_text(
        json.dumps({"backup_count": 1}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
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
    assert "PRODUCT_DECISION_CLI_ERROR=ValueError" in result.stderr
    assert not output_path.exists()


def test_cli_source_has_no_network_random_or_manual_override_markers():
    source = CLI_PATH.read_text(encoding="utf-8")

    forbidden_markers = [
        "requests",
        "httpx",
        "urllib",
        "socket",
        "random",
        "manual_override",
        "manual_pick",
        "operator_selected_champion",
    ]

    found = [marker for marker in forbidden_markers if marker in source]
    assert found == []
