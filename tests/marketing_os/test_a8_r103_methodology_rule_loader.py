from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from synapse.marketing_os.methodology_rule_loader import (
    EXPECTED_FIXTURE_SCHEMA_VERSION,
    EXPECTED_SCENARIO_COUNT,
    MethodologyRuleLoaderError,
    load_and_validate_adversarial_fixtures,
    load_json_document,
    load_methodology_contract,
    validate_adversarial_fixtures,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "phase1" / "A8_R101_MARKETING_METHOD_DEPTH_SPEC.json"
FIXTURES = ROOT / "tests" / "fixtures" / "marketing_methodology" / "a8_r103_adversarial_fixtures.json"
MODULE = ROOT / "synapse" / "marketing_os" / "methodology_rule_loader.py"


def test_a8_r103_loads_r101_spec_from_disk_and_builds_r102_contract() -> None:
    loaded = load_methodology_contract(SPEC)

    assert loaded.source_path == SPEC
    assert loaded.spec["schema_version"] == "synapse.marketing_methodology.depth.v1"
    assert loaded.contract.framework_count == 15
    assert loaded.contract.rule_count == 82
    assert len(loaded.contract.global_anti_generic_gates) == 8
    assert len(loaded.contract.adversarial_scenarios) == 8


def test_a8_r103_loads_and_executes_all_adversarial_fixtures() -> None:
    loaded = load_methodology_contract(SPEC)
    report = load_and_validate_adversarial_fixtures(FIXTURES, loaded.contract)

    assert report.schema_version == EXPECTED_FIXTURE_SCHEMA_VERSION
    assert report.scenario_count == EXPECTED_SCENARIO_COUNT == 8
    assert report.passed is True
    assert {item.scenario_id for item in report.results} == {f"ADV-00{i}" for i in range(1, 9)}
    assert any(item.predicate_matched is False for item in report.results)
    assert any(item.predicate_matched is True for item in report.results)

    by_id = {item.scenario_id: item for item in report.results}
    assert by_id["ADV-001"].missing_fields == ("product_facts",)
    assert by_id["ADV-002"].missing_fields == ("proof_available",)
    assert by_id["ADV-005"].target_rule_id == "ANG-D001"
    assert "tie_break_applied" in by_id["ADV-005"].must_trigger


def test_a8_r103_fixture_ids_must_match_contract_adversarial_scenarios() -> None:
    loaded = load_methodology_contract(SPEC)
    bundle = dict(load_json_document(FIXTURES))
    scenarios = list(bundle["scenarios"])
    scenarios.pop()
    bundle["scenarios"] = scenarios

    with pytest.raises(MethodologyRuleLoaderError):
        validate_adversarial_fixtures(bundle, loaded.contract)


def test_a8_r103_unknown_target_rule_fails_closed() -> None:
    loaded = load_methodology_contract(SPEC)
    bundle = json.loads(FIXTURES.read_text(encoding="utf-8"))
    bundle["scenarios"][0]["target_rule_id"] = "UNKNOWN-RULE"

    with pytest.raises(MethodologyRuleLoaderError):
        validate_adversarial_fixtures(bundle, loaded.contract)


def test_a8_r103_expected_predicate_mismatch_fails_closed() -> None:
    loaded = load_methodology_contract(SPEC)
    bundle = json.loads(FIXTURES.read_text(encoding="utf-8"))
    bundle["scenarios"][0]["expected_predicate_matched"] = True

    with pytest.raises(MethodologyRuleLoaderError):
        validate_adversarial_fixtures(bundle, loaded.contract)


def test_a8_r103_loader_rejects_invalid_json_or_wrong_suffix(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(MethodologyRuleLoaderError):
        load_json_document(missing)

    wrong_suffix = tmp_path / "fixture.txt"
    wrong_suffix.write_text("{}", encoding="utf-8")
    with pytest.raises(MethodologyRuleLoaderError):
        load_json_document(wrong_suffix)

    invalid = tmp_path / "broken.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(MethodologyRuleLoaderError):
        load_json_document(invalid)


def test_a8_r103_module_is_loader_not_engine_or_live_path() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))

    forbidden_import_roots = {
        "os",
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "urllib",
        "ftplib",
        "smtplib",
    }
    imported_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert not (imported_roots & forbidden_import_roots)

    text = MODULE.read_text(encoding="utf-8").lower()
    forbidden_terms = [
        "requests.",
        "httpx.",
        "socket.",
        "subprocess.",
        "spend_authorization",
        "create_ad",
        "publish",
        "fulfillment",
        "order_create",
        "replace_category_angle",
    ]
    for term in forbidden_terms:
        assert term not in text


def test_a8_r103_does_not_change_r102_contract_counts() -> None:
    loaded = load_methodology_contract(SPEC)
    report = load_and_validate_adversarial_fixtures(FIXTURES, loaded.contract)

    assert loaded.contract.framework_count == 15
    assert loaded.contract.rule_count == 82
    assert report.scenario_count == 8