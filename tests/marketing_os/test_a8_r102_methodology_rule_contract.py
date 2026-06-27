from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from synapse.marketing_os.methodology_rule_contract import (
    EXPECTED_FRAMEWORK_COUNT,
    EXPECTED_RULE_COUNT,
    MethodologyRuleContractError,
    build_contract,
    evaluate_predicate,
    iter_rules,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "phase1" / "A8_R101_MARKETING_METHOD_DEPTH_SPEC.json"
MODULE = ROOT / "synapse" / "marketing_os" / "methodology_rule_contract.py"


def load_spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def test_a8_r102_builds_contract_from_r101_spec_without_changing_counts() -> None:
    contract = build_contract(load_spec())

    assert contract.framework_count == EXPECTED_FRAMEWORK_COUNT == 15
    assert contract.rule_count == EXPECTED_RULE_COUNT == 82
    assert len(contract.global_anti_generic_gates) == 8
    assert len(contract.adversarial_scenarios) == 8
    assert contract.no_code_conversion_source is True
    assert contract.no_loader_source is True
    assert contract.no_engine_source is True


def test_a8_r102_preserves_rule_identity_priority_source_anchor_and_trace() -> None:
    contract = build_contract(load_spec())
    rules = iter_rules(contract)

    assert len(rules) == 82
    assert len({rule.id for rule in rules}) == 82

    angle_rule = next(rule for rule in rules if rule.id == "ANG-D001")
    assert angle_rule.source_anchor == "PERSUASION"
    assert angle_rule.priority == 99
    assert "rule_id" in angle_rule.trace_fields
    assert "source_anchor" in angle_rule.trace_fields
    assert angle_rule.predicate.predicate_id == "predicate:ANG-D001"
    assert "proof_available" in angle_rule.predicate.required_presence_fields


def test_a8_r102_predicates_are_machine_evaluable() -> None:
    contract = build_contract(load_spec())
    angle_rule = next(rule for rule in iter_rules(contract) if rule.id == "ANG-D001")

    positive = evaluate_predicate(
        angle_rule.predicate,
        {
            "product_facts": ["foldable", "leak resistant"],
            "proof_available": ["demo photo"],
            "claim_risk": "low",
            "channel": "Meta",
            "buyer_state": "problem-aware",
            "margin_profile": "acceptable",
        },
    )
    assert positive.matched is True
    assert positive.missing_fields == ()

    negative = evaluate_predicate(
        angle_rule.predicate,
        {
            "product_facts": ["foldable"],
            "proof_available": [],
            "claim_risk": "low",
            "channel": "Meta",
            "buyer_state": "problem-aware",
            "margin_profile": "acceptable",
        },
    )
    assert negative.matched is False
    assert "proof_available" in negative.missing_fields


def test_a8_r102_rejects_invalid_or_degraded_r101_spec() -> None:
    data = load_spec()
    data["frameworks"][0]["decision_rules"][0]["source_anchor"] = "UNSUPPORTED"
    with pytest.raises(MethodologyRuleContractError):
        build_contract(data)

    data = load_spec()
    data["frameworks"][0]["decision_rules"][0]["deterministic"] = False
    with pytest.raises(MethodologyRuleContractError):
        build_contract(data)

    data = load_spec()
    data["frameworks"][0]["decision_rules"][0]["trace_fields"] = ["framework"]
    with pytest.raises(MethodologyRuleContractError):
        build_contract(data)


def test_a8_r102_frameworks_keep_route_examples_and_tie_breaks() -> None:
    contract = build_contract(load_spec())

    for framework in contract.frameworks:
        assert set(framework.route_example_types) == {"acceptance", "fallback", "rejection"}
        assert framework.tie_break_order
        assert framework.overlap_policy
        assert framework.fallback_policy
        priorities = [rule.priority for rule in framework.rules]
        assert len(priorities) == len(set(priorities))


def test_a8_r102_module_has_no_loader_engine_network_subprocess_or_live_terms() -> None:
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
        "open(",
        "path(",
        "requests.",
        "httpx.",
        "socket.",
        "subprocess.",
        "meta live",
        "shopify live",
        "dropi live",
        "spend_authorization",
        "create_ad",
        "publish",
        "fulfillment",
        "order_create",
    ]
    for term in forbidden_terms:
        assert term not in text


def test_a8_r102_does_not_modify_r101_source_spec() -> None:
    source = load_spec()
    contract = build_contract(source)

    assert source["schema_version"] == "synapse.marketing_methodology.depth.v1"
    assert contract.rule_count == sum(len(fw["decision_rules"]) for fw in source["frameworks"])