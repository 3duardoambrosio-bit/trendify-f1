
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "phase1" / "A8_R100_MARKETING_METHOD_SPEC.json"

REQUIRED_FIELDS = [
    "name",
    "purpose",
    "accepted_inputs",
    "required_outputs",
    "preconditions",
    "decision_rules",
    "rejection_rules",
    "trace_fields",
    "source_anchors",
    "conversion_target",
    "anti_generic_rules",
    "determinism",
    "worked_example",
]


def load_spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def test_a8_r100_spec_exists_and_scope_is_safe() -> None:
    data = load_spec()
    assert data["schema_version"] == "synapse.marketing_methodology.v1"
    assert data["island"] == "A8-R100I1"
    assert data["type"] == "methodology_spec_no_engine_no_loader"
    assert data["does_not_certify_market_performance"] is True
    assert data["does_not_certify_marketing_expert_engine"] is True
    safety = data["safety"]
    assert safety["operator_en_control"] is True
    for key in ("live_meta", "live_shopify", "live_dropi", "live_write", "real_spend", "orders", "fulfillment"):
        assert safety[key] is False


def test_a8_r100_has_exact_required_framework_count() -> None:
    data = load_spec()
    frameworks = data["frameworks"]
    assert len(frameworks) == data["audit_gates"]["required_framework_count"] == 15


def test_a8_r100_every_framework_has_required_fields_populated() -> None:
    data = load_spec()
    for fw in data["frameworks"]:
        missing = [field for field in REQUIRED_FIELDS if field not in fw]
        assert missing == [], f"{fw.get('name')} missing {missing}"
        for field in REQUIRED_FIELDS:
            assert fw[field] not in (None, "", [], {}), f"{fw['name']} empty {field}"


def test_a8_r100_every_framework_has_source_anchor_and_anti_generic_rule() -> None:
    data = load_spec()
    for fw in data["frameworks"]:
        assert len(fw["source_anchors"]) >= 1, fw["name"]
        assert len(fw["anti_generic_rules"]) >= 1, fw["name"]


def test_a8_r100_every_framework_is_deterministic() -> None:
    data = load_spec()
    for fw in data["frameworks"]:
        det = fw["determinism"]
        assert det["required"] is True, fw["name"]
        assert det["tie_break_order"], fw["name"]
        assert "overlap_policy" in det and det["overlap_policy"], fw["name"]
        assert "fallback_policy" in det and det["fallback_policy"], fw["name"]


def test_a8_r100_every_framework_has_worked_example_with_trace() -> None:
    data = load_spec()
    for fw in data["frameworks"]:
        ex = fw["worked_example"]
        assert ex["input"], fw["name"]
        assert ex["rule_application"], fw["name"]
        assert ex["output"], fw["name"]
        trace = ex["trace"]
        assert trace["framework"] == fw["name"]
        assert trace["rule_ids_applied"], fw["name"]
        assert "fallback_used" in trace, fw["name"]
        assert "operator_review_required" in trace, fw["name"]


def test_a8_r100_declares_replacement_of_category_angle_without_implementing_engine() -> None:
    data = load_spec()
    assert "_category_angle" in data["replaces"]
    assert data["type"] == "methodology_spec_no_engine_no_loader"
    assert "A8-R103 Atlas/methodology-grounded marketing decision engine" in data["future_sequence"]
