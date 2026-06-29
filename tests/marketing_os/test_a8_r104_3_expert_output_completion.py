from __future__ import annotations

import ast
import json
from pathlib import Path

from synapse.marketing_os.methodology_decision_engine import (
    MethodologyDecisionInput,
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


def _decisions() -> dict[str, object]:
    loaded = load_methodology_contract(SPEC)
    return {
        case["id"]: decide_marketing_methodology(loaded.contract, _input_from_case(case))
        for case in _load_cases()
    }


def test_a8_r104_3_decision_identity_is_preserved() -> None:
    observed = {
        case_id: (decision.status, decision.selected_rule_id)
        for case_id, decision in _decisions().items()
    }

    assert observed == {
        "R105-CASE-001": ("blocked", "CLR-D003"),
        "R105-CASE-002": ("accepted", "ANG-D001"),
        "R105-CASE-003": ("blocked", "OFF-D002"),
        "R105-CASE-004": ("blocked", "CLR-D003"),
        "R105-CASE-005": ("blocked", "AGR-D001"),
        "R105-CASE-006": ("accepted", "ANG-D001"),
        "R105-CASE-007": ("blocked", "CLR-D003"),
        "R105-CASE-008": ("blocked", "CLR-D003"),
    }


def test_a8_r104_3_accepted_outputs_include_offer_margin_construction() -> None:
    decisions = _decisions()

    for case_id in ("R105-CASE-002", "R105-CASE-006"):
        text = decisions[case_id].safe_output
        assert decisions[case_id].status == "accepted"
        assert "Offer/margin:" in text
        assert "margin" in text.lower()
        assert "bundle" in text.lower() or "threshold offer" in text.lower() or "margin-safe" in text.lower()
        assert "discount-first" in text.lower() or "do not lead with price" in text.lower() or "proof-led bundle" in text.lower()
        assert "CTA:" in text
        assert "Operator asset:" in text


def test_a8_r104_3_buyer_fit_and_channel_are_not_byte_identical_between_accepted_cases() -> None:
    decisions = _decisions()

    pet = decisions["R105-CASE-002"].safe_output
    travel = decisions["R105-CASE-006"].safe_output

    def segment(text: str, start: str, end: str) -> str:
        s = text.index(start)
        e = text.index(end, s)
        return text[s:e]

    pet_buyer = segment(pet, "Buyer fit:", "Objection handled:")
    travel_buyer = segment(travel, "Buyer fit:", "Objection handled:")
    pet_channel = segment(pet, "Meta note:", "Operator asset:")
    travel_channel = segment(travel, "Meta note:", "Operator asset:")

    assert pet_buyer != travel_buyer
    assert pet_channel != travel_channel
    assert "pet hair" in pet_buyer.lower()
    assert "travel" in travel_buyer.lower() or "bag" in travel_buyer.lower() or "leak" in travel_buyer.lower()
    assert "messy fabric" in pet_channel.lower()
    assert "travel/bag problem" in travel_channel.lower()


def test_a8_r104_3_claim_safety_reasons_are_product_specific() -> None:
    decisions = _decisions()

    claim_cases = {
        "R105-CASE-001": "beauty",
        "R105-CASE-004": "posture",
        "R105-CASE-007": "car",
        "R105-CASE-008": "blender",
    }

    primary_reasons = {}
    for case_id, expected_word in claim_cases.items():
        decision = decisions[case_id]
        text = decision.safe_output
        assert decision.status == "blocked"
        assert decision.selected_rule_id == "CLR-D003"
        assert "Primary reason:" in text
        assert expected_word in text.lower()
        assert "Operator review required" in text
        assert "operator_review_required" not in text
        primary_reasons[case_id] = text.split("Evidence checked:", 1)[0]

    assert len(set(primary_reasons.values())) == len(primary_reasons)


def test_a8_r104_3_margin_and_generic_blocks_remain_specific() -> None:
    decisions = _decisions()

    kitchen = decisions["R105-CASE-003"].safe_output
    led = decisions["R105-CASE-005"].safe_output

    assert "offer economics" in kitchen.lower()
    assert "margin" in kitchen.lower()
    assert "bundle value" in kitchen.lower() or "margin-safe framing" in kitchen.lower()
    assert "broad discount" in kitchen.lower()

    assert "generic positioning" in led.lower()
    assert "specific product fact" in led.lower() or "visible use case" in led.lower()
    assert "category-only" in led.lower() or "lookalike" in led.lower()


def test_a8_r104_3_cold_buyer_gating_remains_blocked() -> None:
    loaded = load_methodology_contract(SPEC)
    cold = MethodologyDecisionInput(
        product_facts=("aluminum laptop stand", "angle adjustment demo"),
        buyer_state="cold",
        proof_available=("desk setup demo", "height comparison visual"),
        claim_risk="medium",
        channel="Meta",
        margin_profile="healthy",
        candidate_output="Improves desk comfort with visible adjustment",
        category="laptop stand",
    )

    decision = decide_marketing_methodology(loaded.contract, cold)

    assert decision.status == "blocked"
    assert decision.selected_rule_id == "CTA-D002"
    assert "Operator review required" in decision.safe_output


def test_a8_r104_3_engine_has_no_live_network_or_spend_paths() -> None:
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