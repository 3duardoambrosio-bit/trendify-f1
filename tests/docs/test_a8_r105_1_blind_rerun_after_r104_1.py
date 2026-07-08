from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs" / "phase1" / "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
ORIGINAL_OUTPUTS = ROOT / "docs" / "phase1" / "A8_R105_ENGINE_OUTPUTS_FOR_EXPERT_AUDIT.json"
RERUN_OUTPUTS = ROOT / "docs" / "phase1" / "A8_R105_1_ENGINE_OUTPUTS_AFTER_R104_1_REMEDIATION.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_a8_r105_1_uses_same_blind_protocol_cases() -> None:
    protocol = load_json(PROTOCOL)
    rerun = load_json(RERUN_OUTPUTS)

    protocol_ids = [case["id"] for case in protocol["blind_cases"]]
    rerun_ids = [case["case_id"] for case in rerun["case_outputs"]]

    assert rerun["schema_version"] == "synapse.marketing_expert_audit_outputs.v2"
    assert rerun["island"] == "A8-R105.1"
    assert rerun["source_protocol"] == "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
    assert rerun["source_engine"] == "A8-R104.1"
    assert rerun["r105_protocol_unchanged"] is True
    assert rerun_ids == protocol_ids
    assert rerun["case_count"] == 8


def test_a8_r105_1_outputs_are_evidence_not_ground_truth() -> None:
    rerun = load_json(RERUN_OUTPUTS)

    assert rerun["engine_outputs_are_not_ground_truth"] is True
    assert rerun["requires_external_expert_scoring"] is True

    for item in rerun["case_outputs"]:
        assert item["expert_score_required"] is True
        assert "not ground truth" in item["note"]


def test_a8_r105_1_rerun_no_longer_collapses_to_uniform_block() -> None:
    rerun = load_json(RERUN_OUTPUTS)
    summary = rerun["summary"]

    assert summary["all_blocked"] is False
    assert summary["all_aud_d001"] is False
    assert summary["all_outputs_identical"] is False
    assert set(summary["statuses"]) >= {"accepted", "blocked"}
    assert "AUD-D001" not in summary["selected_rule_ids"]


def test_a8_r105_1_expected_remediation_patterns_are_present() -> None:
    rerun = load_json(RERUN_OUTPUTS)
    by_id = {item["case_id"]: item["engine_output"] for item in rerun["case_outputs"]}

    assert by_id["R105-CASE-002"]["status"] == "accepted"
    assert by_id["R105-CASE-002"]["selected_rule_id"] == "ANG-D001"
    assert "manual reusable roller" in by_id["R105-CASE-002"]["safe_output"]

    assert by_id["R105-CASE-006"]["status"] == "accepted"
    assert by_id["R105-CASE-006"]["selected_rule_id"] == "ANG-D001"
    assert "foldable silicone bottle" in by_id["R105-CASE-006"]["safe_output"]

    assert by_id["R105-CASE-003"]["status"] == "blocked"
    assert by_id["R105-CASE-003"]["selected_rule_id"] == "OFF-D002"

    assert by_id["R105-CASE-005"]["status"] == "blocked"
    assert by_id["R105-CASE-005"]["selected_rule_id"] == "AGR-D001"

    for case_id in ("R105-CASE-001", "R105-CASE-004", "R105-CASE-007", "R105-CASE-008"):
        assert by_id[case_id]["status"] == "blocked"
        assert by_id[case_id]["operator_review_required"] is True
        assert by_id[case_id]["selected_rule_id"] == "CLR-D003"


def test_a8_r105_1_original_failed_outputs_remain_available_for_comparison() -> None:
    original = load_json(ORIGINAL_OUTPUTS)
    rerun = load_json(RERUN_OUTPUTS)

    assert original["case_count"] == rerun["case_count"] == 8
    assert original["engine_outputs_are_not_ground_truth"] is True

    original_outputs = {
        item["case_id"]: item["engine_output"]["safe_output"]
        for item in original["case_outputs"]
    }
    rerun_outputs = {
        item["case_id"]: item["engine_output"]["safe_output"]
        for item in rerun["case_outputs"]
    }

    assert original_outputs != rerun_outputs


def test_a8_r105_1_protocol_still_has_independence_controls() -> None:
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