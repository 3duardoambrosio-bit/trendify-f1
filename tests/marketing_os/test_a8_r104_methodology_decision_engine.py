from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from synapse.marketing_os.methodology_decision_engine import (
    MethodologyDecisionEngineError,
    MethodologyDecisionInput,
    category_angle_from_methodology,
    decide_marketing_methodology,
    decision_input_from_fixture_context,
    enforce_adversarial_must_triggers,
    evaluate_rule_decision,
    load_default_engine_inputs,
    run_engine_against_adversarial_fixtures,
)
from synapse.marketing_os.methodology_rule_loader import load_json_document, load_methodology_contract

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "phase1" / "A8_R101_MARKETING_METHOD_DEPTH_SPEC.json"
FIXTURES = ROOT / "tests" / "fixtures" / "marketing_methodology" / "a8_r103_adversarial_fixtures.json"
ENGINE = ROOT / "synapse" / "marketing_os" / "methodology_decision_engine.py"


def test_a8_r104_runs_engine_against_r101_r102_r103_chain() -> None:
    report = run_engine_against_adversarial_fixtures(SPEC, FIXTURES)

    assert report.loaded.contract.framework_count == 15
    assert report.loaded.contract.rule_count == 82
    assert report.fixture_report.scenario_count == 8
    assert report.fixture_report.passed is True
    assert report.decision.schema_version == "synapse.marketing_methodology.decision_engine.v1"


def test_a8_r104_enforces_all_adversarial_must_triggers() -> None:
    loaded = load_methodology_contract(SPEC)
    fixture_bundle = load_json_document(FIXTURES)

    decisions = enforce_adversarial_must_triggers(fixture_bundle, loaded.contract)

    assert len(decisions) == 8
    trigger_set = {trigger for decision in decisions for trigger in decision.triggers}
    assert "generic_rejected" in trigger_set
    assert "claim_rejected" in trigger_set
    assert "safe_rewrite" in trigger_set
    assert "reject_discount_offer" in trigger_set
    assert "tie_break_applied" in trigger_set
    assert "channel_constraint" in trigger_set
    assert "cta_softened_or_rejected" in trigger_set
    assert any(decision.blocked for decision in decisions)


def test_a8_r104_uses_semantic_value_checks_not_presence_only() -> None:
    loaded = load_methodology_contract(SPEC)

    high_risk = MethodologyDecisionInput(
        product_facts=("skin contact accessory",),
        buyer_state="skeptical",
        proof_available=("source attribute",),
        claim_risk="high",
        channel="Meta",
        margin_profile="acceptable",
        category="test product",
    )
    low_risk = MethodologyDecisionInput(
        product_facts=("skin contact accessory",),
        buyer_state="skeptical",
        proof_available=("source attribute",),
        claim_risk="low",
        channel="Meta",
        margin_profile="acceptable",
        category="test product",
    )

    high = evaluate_rule_decision(loaded.contract, "CLR-D003", high_risk)
    low = evaluate_rule_decision(loaded.contract, "CLR-D003", low_risk)

    assert high.predicate_matched is True
    assert high.semantic_matched is True
    assert "claim_rejected" in high.triggers

    assert low.predicate_matched is True
    assert low.semantic_matched is False
    assert "claim_rejected" not in low.triggers


def test_a8_r104_decision_status_and_safe_output_are_deterministic() -> None:
    loaded = load_methodology_contract(SPEC)
    decision_input = MethodologyDecisionInput(
        product_facts=("foldable", "leak resistant"),
        buyer_state="problem-aware",
        proof_available=("demo photo",),
        claim_risk="low",
        channel="Meta",
        margin_profile="acceptable",
        category="travel bottle",
    )

    first = decide_marketing_methodology(loaded.contract, decision_input, candidate_rule_ids=("ANG-D001",))
    second = decide_marketing_methodology(loaded.contract, decision_input, candidate_rule_ids=("ANG-D001",))

    assert first == second
    assert first.status == "accepted"
    assert first.selected_rule_id == "ANG-D001"
    assert "demo_angle" in first.triggers
    assert "travel bottle" in first.safe_output


def test_a8_r104_fails_closed_when_must_trigger_is_not_emitted() -> None:
    loaded = load_methodology_contract(SPEC)
    fixture_bundle = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture_bundle["scenarios"][0]["must_trigger"] = ["nonexistent_required_trigger"]

    with pytest.raises(MethodologyDecisionEngineError):
        enforce_adversarial_must_triggers(fixture_bundle, loaded.contract)


def test_a8_r104_category_angle_legacy_function_is_patched_to_engine() -> None:
    candidates = []
    for path in (ROOT / "synapse" / "marketing_os").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "def _category_angle" in text:
            candidates.append(path)

    assert len(candidates) == 1
    patched_text = candidates[0].read_text(encoding="utf-8")
    assert "category_angle_from_methodology" in patched_text

    spec = importlib.util.spec_from_file_location("category_angle_target", candidates[0])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    output = module._category_angle("travel bottle")
    assert isinstance(output, tuple)
    assert len(output) == 3
    assert any("travel bottle" in part for part in output)
    assert any("Show the" in part for part in output)


def test_a8_r104_engine_module_has_no_external_or_live_paths() -> None:
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))

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

    text = ENGINE.read_text(encoding="utf-8").lower()
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
    ]
    for term in forbidden_terms:
        assert term not in text


def test_a8_r104_fixture_context_adapter_is_deterministic() -> None:
    fixture_bundle = load_json_document(FIXTURES)
    scenario = fixture_bundle["scenarios"][4]
    left = decision_input_from_fixture_context(scenario["context"])
    right = decision_input_from_fixture_context(scenario["context"])

    assert left == right
    assert left.product_facts == ("foldable", "leak resistant")
    assert left.channel == "Meta"