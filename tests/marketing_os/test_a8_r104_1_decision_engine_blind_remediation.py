from __future__ import annotations

import ast
import json
from pathlib import Path

from synapse.marketing_os.methodology_decision_engine import (
    MethodologyDecisionInput,
    category_angle_from_methodology,
    decide_marketing_methodology,
)
from synapse.marketing_os.methodology_rule_loader import load_methodology_contract

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "phase1" / "A8_R101_MARKETING_METHOD_DEPTH_SPEC.json"
PROTOCOL = ROOT / "docs" / "phase1" / "A8_R105_MARKETING_EXPERT_AUDIT_PROTOCOL.json"
ENGINE = ROOT / "synapse" / "marketing_os" / "methodology_decision_engine.py"


def _load_cases() -> list[dict]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    return protocol["blind_cases"]


def _input_from_case(case: dict) -> MethodologyDecisionInput:
    product = case["product"]
    buyer = case["buyer_context"]
    claims_text = " ".join(product["supplier_claims"]).lower()
    high_terms = ("pain", "wrinkle", "anti-aging", "fixes", "relieves", "never", "crushes ice")

    return MethodologyDecisionInput(
        product_facts=tuple(product["facts"]),
        buyer_state=str(buyer["buyer_state"]),
        proof_available=tuple(product["available_proof"]),
        claim_risk="high" if any(term in claims_text for term in high_terms) else "medium",
        channel=str(case["channel"]),
        margin_profile=str(product["margin_profile"]),
        candidate_output=" ".join(product["supplier_claims"]),
        category=str(product["category"]),
    )


def test_a8_r104_1_r105_blind_cases_no_longer_collapse_to_aud_d001_block_all() -> None:
    loaded = load_methodology_contract(SPEC)
    decisions = [
        decide_marketing_methodology(loaded.contract, _input_from_case(case))
        for case in _load_cases()
    ]

    assert len(decisions) == 8
    assert len({decision.status for decision in decisions}) >= 2
    assert len({decision.selected_rule_id for decision in decisions}) >= 3
    assert len({decision.safe_output for decision in decisions}) >= 6

    assert not all(decision.status == "blocked" for decision in decisions)
    assert not all(decision.selected_rule_id == "AUD-D001" for decision in decisions)
    assert not all("Blocked by AUD-D001" in decision.safe_output for decision in decisions)


def test_a8_r104_1_clean_proof_cases_get_accepted_specific_angles() -> None:
    loaded = load_methodology_contract(SPEC)
    cases = {case["id"]: case for case in _load_cases()}

    for case_id, expected_fact in {
        "R105-CASE-002": "manual reusable roller",
        "R105-CASE-006": "foldable silicone bottle",
    }.items():
        decision = decide_marketing_methodology(loaded.contract, _input_from_case(cases[case_id]))

        assert decision.status == "accepted"
        assert decision.selected_rule_id == "ANG-D001"
        assert decision.operator_review_required is False
        assert expected_fact in decision.safe_output
        assert cases[case_id]["product"]["category"] in decision.safe_output


def test_a8_r104_1_risky_or_unsupported_cases_remain_blocked_with_specific_evidence() -> None:
    loaded = load_methodology_contract(SPEC)
    cases = {case["id"]: case for case in _load_cases()}

    for case_id in ("R105-CASE-001", "R105-CASE-004", "R105-CASE-007", "R105-CASE-008"):
        case = cases[case_id]
        decision = decide_marketing_methodology(loaded.contract, _input_from_case(case))

        assert decision.status == "blocked"
        assert decision.operator_review_required is True
        assert case["product"]["category"] in decision.safe_output
        assert any(fact in decision.safe_output for fact in case["product"]["facts"][:2])
        assert "Operator review required" in decision.safe_output


def test_a8_r104_1_tight_margin_or_generic_cases_do_not_get_unqualified_approval() -> None:
    loaded = load_methodology_contract(SPEC)
    cases = {case["id"]: case for case in _load_cases()}

    kitchen = decide_marketing_methodology(loaded.contract, _input_from_case(cases["R105-CASE-003"]))
    led = decide_marketing_methodology(loaded.contract, _input_from_case(cases["R105-CASE-005"]))

    assert kitchen.status in {"blocked", "fallback"}
    assert kitchen.selected_rule_id in {"OFF-D002", "OFF-D006", "ANG-D005", "PRF-D006", "CTA-D002"}

    assert led.status in {"blocked", "fallback"}
    assert led.selected_rule_id in {"AGR-D001", "AGR-D003", "HOK-D008", "CTA-D002"}


def test_a8_r104_1_category_angle_wrapper_still_returns_legacy_tuple() -> None:
    output = category_angle_from_methodology("travel bottle")

    assert isinstance(output, tuple)
    assert len(output) == 3
    assert all(isinstance(item, str) for item in output)
    assert any("travel bottle" in item for item in output)


def test_a8_r104_1_engine_has_no_live_network_or_spend_paths() -> None:
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