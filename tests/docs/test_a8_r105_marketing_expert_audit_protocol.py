from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs" / "phase1" / "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
OUTPUTS = ROOT / "docs" / "phase1" / "A8_R105_ENGINE_OUTPUTS_FOR_EXPERT_AUDIT.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_a8_r105_protocol_is_independent_expert_audit_pack() -> None:
    data = load_json(PROTOCOL)

    assert data["schema_version"] == "synapse.marketing_expert_audit_protocol.v1"
    assert data["island"] == "A8-R105"
    assert data["type"] == "independent_expert_audit_pack_no_engine_change_no_live_no_spend"

    controls = data["independence_controls"]
    assert controls["blind_cases"] is True
    assert controls["no_target_rule_id"] is True
    assert controls["no_expected_engine_status"] is True
    assert controls["no_expected_engine_trigger"] is True
    assert controls["no_expected_rule_id"] is True
    assert controls["no_engine_tuning_in_this_island"] is True


def test_a8_r105_blind_cases_do_not_contain_engine_expected_answers() -> None:
    data = load_json(PROTOCOL)
    cases = data["blind_cases"]

    assert len(cases) == 8
    forbidden_keys = {
        "target_rule_id",
        "expected_rule_id",
        "expected_engine_status",
        "expected_trigger",
        "expected_predicate_matched",
        "expected_missing_fields",
        "must_trigger",
    }

    for case in cases:
        serialized = json.dumps(case, sort_keys=True)
        for forbidden in forbidden_keys:
            assert forbidden not in case
            assert f'"{forbidden}"' not in serialized


def test_a8_r105_cases_have_marketing_pressure_and_realistic_product_context() -> None:
    data = load_json(PROTOCOL)

    for case in data["blind_cases"]:
        assert case["id"].startswith("R105-CASE-")
        assert case["product"]["category"]
        assert len(case["product"]["facts"]) >= 3
        assert len(case["product"]["supplier_claims"]) >= 1
        assert len(case["product"]["available_proof"]) >= 1
        assert case["product"]["margin_profile"] in {"tight", "acceptable"}
        assert case["buyer_context"]["buyer_state"]
        assert len(case["buyer_context"]["objections"]) >= 2
        assert case["channel"] == "Meta"
        assert len(case["audit_pressure"]) >= 3


def test_a8_r105_rubric_requires_expert_marketing_quality_not_structure_only() -> None:
    data = load_json(PROTOCOL)
    rubric = data["expert_scoring_rubric"]
    criteria = rubric["criteria"]

    assert rubric["minimum_close_threshold"]["overall_average_min"] == 4.0
    assert rubric["minimum_close_threshold"]["safety_claims_min"] == 5.0
    assert rubric["minimum_close_threshold"]["anti_generic_min"] == 4.0

    ids = {item["id"] for item in criteria}
    assert {
        "specificity",
        "buyer_state_fit",
        "proof_discipline",
        "claim_safety",
        "offer_margin_fit",
        "channel_fit",
        "anti_generic",
        "decision_usefulness",
    } == ids


def test_a8_r105_engine_outputs_are_evidence_not_ground_truth() -> None:
    outputs = load_json(OUTPUTS)

    assert outputs["schema_version"] == "synapse.marketing_expert_audit_outputs.v1"
    assert outputs["island"] == "A8-R105"
    assert outputs["case_count"] == 8
    assert outputs["engine_outputs_are_not_ground_truth"] is True
    assert outputs["requires_external_expert_scoring"] is True

    case_outputs = outputs["case_outputs"]
    assert len(case_outputs) == 8
    assert {item["case_id"] for item in case_outputs} == {f"R105-CASE-00{i}" for i in range(1, 9)}

    for item in case_outputs:
        engine_output = item["engine_output"]
        assert engine_output["schema_version"] == "synapse.marketing_methodology.decision_engine.v1"
        assert engine_output["selected_rule_id"]
        assert engine_output["selected_framework"]
        assert engine_output["status"] in {"accepted", "blocked", "fallback"}
        assert isinstance(engine_output["triggers"], list)
        assert isinstance(engine_output["operator_review_required"], bool)
        assert isinstance(engine_output["safe_output"], str)
        assert item["expert_score_required"] is True
        assert "not an expected-correct answer" in item["note"]


def test_a8_r105_safety_non_goals_are_explicit() -> None:
    data = load_json(PROTOCOL)
    text = json.dumps(data, sort_keys=True).lower()

    assert "no live meta" in text
    assert "no spend" in text
    assert "no external writes" in text
    assert "no order creation" in text
    assert "no commerce-side action" in text
    assert "no market validation claim" in text