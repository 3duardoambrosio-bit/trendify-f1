from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs" / "phase1" / "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
RERUN_OUTPUTS = ROOT / "docs" / "phase1" / "A8_R105_2_ENGINE_OUTPUTS_AFTER_R104_2_OUTPUT_CRAFT.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_a8_r105_2_uses_same_blind_protocol_cases() -> None:
    protocol = load_json(PROTOCOL)
    rerun = load_json(RERUN_OUTPUTS)

    protocol_ids = [case["id"] for case in protocol["blind_cases"]]
    rerun_ids = [case["case_id"] for case in rerun["case_outputs"]]

    assert rerun["schema_version"] == "synapse.marketing_expert_audit_outputs.v3"
    assert rerun["island"] == "A8-R105.2"
    assert rerun["source_protocol"] == "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
    assert rerun["source_engine"] == "A8-R104.2"
    assert rerun["r105_protocol_unchanged"] is True
    assert rerun_ids == protocol_ids
    assert rerun["case_count"] == 8


def test_a8_r105_2_outputs_are_evidence_not_ground_truth() -> None:
    rerun = load_json(RERUN_OUTPUTS)

    assert rerun["engine_outputs_are_not_ground_truth"] is True
    assert rerun["requires_external_expert_scoring"] is True

    for item in rerun["case_outputs"]:
        assert item["expert_score_required"] is True
        assert "not ground truth" in item["note"]


def test_a8_r105_2_decision_identity_preserved() -> None:
    rerun = load_json(RERUN_OUTPUTS)
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


def test_a8_r105_2_outputs_are_not_collapsed_and_include_craft_markers() -> None:
    rerun = load_json(RERUN_OUTPUTS)
    summary = rerun["summary"]

    assert summary["all_blocked"] is False
    assert summary["all_aud_d001"] is False
    assert summary["all_outputs_identical"] is False
    assert set(summary["statuses"]) >= {"accepted", "blocked"}
    assert "AUD-D001" not in summary["selected_rule_ids"]

    assert summary["accepted_outputs_have_hook"] is True
    assert summary["accepted_outputs_have_buyer_fit"] is True
    assert summary["accepted_outputs_have_objection"] is True
    assert summary["accepted_outputs_have_cta"] is True
    assert summary["accepted_outputs_have_channel_note"] is True
    assert summary["accepted_outputs_have_operator_asset"] is True
    assert summary["blocked_outputs_have_operator_review_required"] is True
    assert summary["blocked_outputs_hide_raw_trigger_noise"] is True


def test_a8_r105_2_accepted_outputs_are_operator_ready_evidence() -> None:
    rerun = load_json(RERUN_OUTPUTS)

    accepted = [
        item["engine_output"]
        for item in rerun["case_outputs"]
        if item["engine_output"]["status"] == "accepted"
    ]
    assert len(accepted) == 2

    for output in accepted:
        text = output["safe_output"]
        assert "Hook:" in text
        assert "Buyer fit:" in text
        assert "Objection handled:" in text
        assert "CTA:" in text
        assert "Meta note:" in text or "Channel note:" in text
        assert "Operator asset:" in text
        assert "Show the " not in text
        assert "use case with concrete proof:" not in text


def test_a8_r105_2_blocked_outputs_are_clean_and_reviewable() -> None:
    rerun = load_json(RERUN_OUTPUTS)

    blocked = [
        item["engine_output"]
        for item in rerun["case_outputs"]
        if item["engine_output"]["status"] == "blocked"
    ]
    assert len(blocked) == 6

    for output in blocked:
        text = output["safe_output"]
        assert "Blocked:" in text
        assert "Primary reason:" in text
        assert "Evidence checked:" in text
        assert "Operator action:" in text
        assert "Operator review required" in text
        assert "Safe next step:" in text
        assert "operator_review_required" not in text
        assert "claim_rejected" not in text
        assert "safe_rewrite" not in text
        assert "channel_constraint" not in text
        assert "cta_softened" not in text


def test_a8_r105_2_protocol_still_has_independence_controls() -> None:
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