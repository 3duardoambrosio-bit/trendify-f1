
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "phase1" / "A8_R101_MARKETING_METHOD_DEPTH_SPEC.json"

EXPECTED_FRAMEWORKS = {
    "AudiencePersona": 5,
    "BuyerStateAwareness": 5,
    "ProductFactExtraction": 5,
    "ValuePropositionPositioning": 5,
    "AngleSelection": 8,
    "OfferConstruction": 6,
    "HookConstruction": 8,
    "ObjectionHandling": 6,
    "ProofRequirement": 6,
    "ClaimRisk": 6,
    "ChannelConstraint": 5,
    "CTA": 5,
    "AntiGenericRejection": 4,
    "DecisionTrace": 4,
    "OperatorReview": 4,
}

ROUTES = {"acceptance", "rejection", "fallback"}


def load_spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def test_a8_r101_scope_is_content_only_and_safe() -> None:
    data = load_spec()
    assert data["schema_version"] == "synapse.marketing_methodology.depth.v1"
    assert data["island"] == "A8-R101"
    assert data["type"] == "content_depth_spec_no_code_conversion_no_loader_no_engine"
    assert data["does_not_certify_market_performance"] is True
    assert data["does_not_certify_marketing_expert_engine"] is True
    gates = data["depth_gates"]
    assert gates["no_code_conversion"] is True
    assert gates["no_loader"] is True
    assert gates["no_engine"] is True
    safety = data["safety"]
    for key in ("live_meta", "live_shopify", "live_dropi", "live_write", "real_spend", "orders", "fulfillment"):
        assert safety[key] is False


def test_a8_r101_frameworks_and_min_rule_counts() -> None:
    data = load_spec()
    frameworks = {fw["name"]: fw for fw in data["frameworks"]}
    assert set(frameworks) == set(EXPECTED_FRAMEWORKS)
    assert len(frameworks) == 15

    for name, minimum in EXPECTED_FRAMEWORKS.items():
        rules = frameworks[name]["decision_rules"]
        assert len(rules) >= minimum, name
        assert frameworks[name]["min_rule_count"] == minimum


def test_a8_r101_every_rule_has_source_anchor_trace_and_determinism() -> None:
    data = load_spec()
    valid_sources = set(data["source_anchors"])

    for fw in data["frameworks"]:
        seen_priorities = set()
        for rule in fw["decision_rules"]:
            for field in ("id", "name", "source_anchor", "source_logic", "when", "then", "priority", "anti_generic_gate", "trace_fields"):
                assert rule[field] not in (None, "", [], {}), f"{fw['name']} {rule.get('id')} empty {field}"
            assert rule["source_anchor"] in valid_sources
            assert rule["deterministic"] is True
            assert rule["priority"] not in seen_priorities
            seen_priorities.add(rule["priority"])
            assert "rule_id" in rule["trace_fields"]
            assert "source_anchor" in rule["trace_fields"]


def test_a8_r101_every_framework_has_three_route_examples() -> None:
    data = load_spec()

    for fw in data["frameworks"]:
        examples = fw["route_examples"]
        assert {ex["type"] for ex in examples} == ROUTES, fw["name"]
        for ex in examples:
            assert ex["input"], fw["name"]
            assert ex["expected_output"], fw["name"]
            assert ex["expected_trace"], fw["name"]


def test_a8_r101_global_anti_generic_gates_are_data() -> None:
    data = load_spec()
    gates = data["global_anti_generic_gates"]
    assert len(gates) >= data["depth_gates"]["global_anti_generic_gates_min"] >= 8
    for gate in gates:
        assert gate["id"].startswith("GLOBAL-AG-")
        assert gate["reject_if"]
        assert gate["reason"]


def test_a8_r101_adversarial_scenarios_are_data() -> None:
    data = load_spec()
    scenarios = data["adversarial_scenarios"]
    assert len(scenarios) >= data["depth_gates"]["adversarial_scenarios_min"] >= 8
    for scenario in scenarios:
        assert scenario["id"].startswith("ADV-")
        assert scenario["name"]
        assert scenario["must_trigger"]


def test_a8_r101_keeps_next_sequence_causal() -> None:
    data = load_spec()
    seq = data["next_sequence"]
    assert seq[0].startswith("A8-R102 executable rule contract")
    assert seq[1].startswith("A8-R103 loader")
    assert seq[2].startswith("A8-R104 marketing decision engine")
    assert seq[3].startswith("A8-R105 external")
