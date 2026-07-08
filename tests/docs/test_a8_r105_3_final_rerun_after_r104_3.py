from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs" / "phase1" / "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
RERUN = ROOT / "docs" / "phase1" / "A8_R105_3_ENGINE_OUTPUTS_AFTER_R104_3_EXPERT_COMPLETION.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_a8_r105_3_uses_same_blind_protocol_cases() -> None:
    protocol = load_json(PROTOCOL)
    rerun = load_json(RERUN)

    protocol_ids = [case["id"] for case in protocol["blind_cases"]]
    rerun_ids = [case["case_id"] for case in rerun["case_outputs"]]

    assert rerun["schema_version"] == "synapse.marketing_expert_audit_outputs.v4"
    assert rerun["island"] == "A8-R105.3"
    assert rerun["source_protocol"] == "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
    assert rerun["source_engine"] == "A8-R104.3"
    assert rerun["r105_protocol_unchanged"] is True
    assert rerun["r105_blind_cases_unchanged"] is True
    assert rerun["engine_changed_in_this_commit"] is False
    assert rerun_ids == protocol_ids
    assert rerun["case_count"] == 8


def test_a8_r105_3_outputs_are_evidence_not_ground_truth() -> None:
    rerun = load_json(RERUN)

    assert rerun["engine_outputs_are_not_ground_truth"] is True
    assert rerun["requires_external_expert_scoring"] is True
    assert rerun["fresh_probes_are_appendix_only"] is True

    for item in rerun["case_outputs"]:
        assert item["expert_score_required"] is True
        assert item["fresh_probe_only"] is False

    for item in rerun["fresh_probe_outputs"]:
        assert item["expert_score_required"] is False
        assert item["fresh_probe_only"] is True


def test_a8_r105_3_decision_identity_preserved() -> None:
    rerun = load_json(RERUN)
    by_id = {item["case_id"]: item["engine_output"] for item in rerun["case_outputs"]}

    assert {
        case_id: (output["status"], output["selected_rule_id"])
        for case_id, output in by_id.items()
    } == {
        "R105-CASE-001": ("blocked", "CLR-D003"),
        "R105-CASE-002": ("accepted", "ANG-D001"),
        "R105-CASE-003": ("blocked", "OFF-D002"),
        "R105-CASE-004": ("blocked", "CLR-D003"),
        "R105-CASE-005": ("blocked", "AGR-D001"),
        "R105-CASE-006": ("accepted", "ANG-D001"),
        "R105-CASE-007": ("blocked", "CLR-D003"),
        "R105-CASE-008": ("blocked", "CLR-D003"),
    }


def test_a8_r105_3_outputs_do_not_collapse() -> None:
    rerun = load_json(RERUN)
    summary = rerun["summary"]

    assert summary["all_blocked"] is False
    assert summary["all_aud_d001"] is False
    assert summary["all_outputs_identical"] is False
    assert set(summary["statuses"]) == {"accepted", "blocked"}
    assert summary["selected_rule_ids"] == ["AGR-D001", "ANG-D001", "CLR-D003", "OFF-D002"]


def test_a8_r105_3_accepted_outputs_cross_completion_requirements() -> None:
    rerun = load_json(RERUN)
    summary = rerun["summary"]

    assert summary["accepted_outputs_have_hook"] is True
    assert summary["accepted_outputs_have_buyer_fit"] is True
    assert summary["accepted_outputs_have_objection"] is True
    assert summary["accepted_outputs_have_offer_margin"] is True
    assert summary["accepted_outputs_have_cta"] is True
    assert summary["accepted_outputs_have_channel_note"] is True
    assert summary["accepted_outputs_have_operator_asset"] is True
    assert summary["accepted_buyer_fit_not_byte_identical"] is True
    assert summary["accepted_channel_note_not_byte_identical"] is True
    assert summary["accepted_outputs_have_margin_safe_language"] is True

    accepted = [
        item["engine_output"]["safe_output"]
        for item in rerun["case_outputs"]
        if item["engine_output"]["status"] == "accepted"
    ]
    assert len(accepted) == 2

    for text in accepted:
        assert "Offer/margin:" in text
        assert "margin" in text.lower()
        assert "margin-safe" in text.lower()
        assert "Hook:" in text
        assert "Buyer fit:" in text
        assert "Objection handled:" in text
        assert "CTA:" in text
        assert "Operator asset:" in text
        assert "Show the " not in text
        assert "use case with concrete proof:" not in text


def test_a8_r105_3_blocked_outputs_are_specific_and_clean() -> None:
    rerun = load_json(RERUN)
    summary = rerun["summary"]

    assert summary["blocked_outputs_have_operator_review_required"] is True
    assert summary["blocked_outputs_have_primary_reason"] is True
    assert summary["blocked_outputs_have_evidence_checked"] is True
    assert summary["blocked_outputs_have_operator_action"] is True
    assert summary["blocked_outputs_have_safe_next_step"] is True
    assert summary["blocked_outputs_hide_raw_trigger_noise"] is True
    assert summary["claim_safety_reasons_product_specific"] is True

    by_id = {item["case_id"]: item["engine_output"]["safe_output"] for item in rerun["case_outputs"]}

    assert "claim safety:" in by_id["R105-CASE-001"]
    assert "beauty" in by_id["R105-CASE-001"].lower() or "skin" in by_id["R105-CASE-001"].lower()
    assert "claim safety:" in by_id["R105-CASE-004"]
    assert "posture" in by_id["R105-CASE-004"].lower() or "pain" in by_id["R105-CASE-004"].lower()
    assert "claim safety:" in by_id["R105-CASE-007"]
    assert "car" in by_id["R105-CASE-007"].lower() or "safety" in by_id["R105-CASE-007"].lower()
    assert "claim safety:" in by_id["R105-CASE-008"]
    assert "blender" in by_id["R105-CASE-008"].lower() or "performance" in by_id["R105-CASE-008"].lower()

    for text in by_id.values():
        assert "operator_review_required" not in text
        assert "claim_rejected" not in text
        assert "safe_rewrite" not in text
        assert "channel_constraint" not in text
        assert "cta_softened" not in text


def test_a8_r105_3_fresh_probe_appendix_exists_without_moving_goalpost() -> None:
    rerun = load_json(RERUN)

    assert rerun["fresh_probe_count"] == 3
    assert len(rerun["fresh_probe_outputs"]) == 3

    for item in rerun["fresh_probe_outputs"]:
        output = item["engine_output"]
        assert item["source"] == "fresh_probe_appendix"
        assert item["fresh_probe_only"] is True
        assert item["expert_score_required"] is False
        assert output["safe_output"]
        assert output["status"] in {"accepted", "blocked", "fallback"}
        assert output["selected_rule_id"]


def test_a8_r105_3_protocol_still_has_independence_controls() -> None:
    protocol = load_json(PROTOCOL)
    controls = protocol["independence_controls"]

    assert controls["blind_cases"] is True
    assert controls["no_target_rule_id"] is True
    assert controls["no_expected_engine_status"] is True
    assert controls["no_expected_engine_trigger"] is True
    assert controls["no_expected_rule_id"] is True
    assert controls["no_engine_tuning_in_this_island"] is True

    for case in protocol["blind_cases"]:
        serialized = json.dumps(case, sort_keys=True)
        assert "target_rule_id" not in serialized
        assert "expected_engine_status" not in serialized
        assert "expected_trigger" not in serialized
        assert "must_trigger" not in serialized