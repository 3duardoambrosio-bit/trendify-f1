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


def _decisions() -> dict[str, object]:
    loaded = load_methodology_contract(SPEC)
    return {
        case["id"]: decide_marketing_methodology(loaded.contract, _input_from_case(case))
        for case in _load_cases()
    }


def test_a8_r104_2_accepted_outputs_are_operator_ready_not_template_only() -> None:
    decisions = _decisions()

    for case_id, expected_fact in {
        "R105-CASE-002": "manual reusable roller",
        "R105-CASE-006": "foldable silicone bottle",
    }.items():
        output = decisions[case_id].safe_output

        assert decisions[case_id].status == "accepted"
        assert decisions[case_id].selected_rule_id == "ANG-D001"
        assert expected_fact in output
        assert "Hook:" in output
        assert "Buyer fit:" in output
        assert "Objection handled:" in output
        assert "CTA:" in output
        assert "Meta note:" in output or "Channel note:" in output
        assert "Operator asset:" in output
        assert "Show the " not in output
        assert "use case with concrete proof:" not in output
        assert len(output) >= 300


def test_a8_r104_2_accepted_outputs_include_buyer_state_channel_and_offer_language() -> None:
    loaded = load_methodology_contract(SPEC)

    warm_input = MethodologyDecisionInput(
        product_facts=("manual reusable roller", "visible before-after cleaning demo"),
        buyer_state="warm",
        proof_available=("before-after demo", "close-up lint removal visual"),
        claim_risk="medium",
        channel="Meta",
        margin_profile="healthy",
        candidate_output="Removes pet hair from sofa fabric",
        category="pet hair remover",
    )
    skeptical_input = MethodologyDecisionInput(
        product_facts=("aluminum laptop stand", "angle adjustment demo"),
        buyer_state="skeptical",
        proof_available=("desk setup demo", "height comparison visual"),
        claim_risk="medium",
        channel="Meta",
        margin_profile="healthy",
        candidate_output="Improves desk comfort with visible adjustment",
        category="laptop stand",
    )

    warm = decide_marketing_methodology(loaded.contract, warm_input)
    skeptical = decide_marketing_methodology(loaded.contract, skeptical_input)

    assert warm.status == "accepted"
    assert skeptical.status == "accepted"
    assert warm.safe_output != skeptical.safe_output
    assert "active pain point" in warm.safe_output or "proof to comparison" in warm.safe_output
    assert "visible proof and reduce trust friction" in skeptical.safe_output
    assert "CTA:" in warm.safe_output
    assert "CTA:" in skeptical.safe_output
    assert "Meta note:" in warm.safe_output
    assert "Meta note:" in skeptical.safe_output


def test_a8_r104_2_blocked_outputs_are_clean_primary_reason_not_trigger_dump() -> None:
    decisions = _decisions()

    for case_id in ("R105-CASE-001", "R105-CASE-004", "R105-CASE-007", "R105-CASE-008"):
        decision = decisions[case_id]
        output = decision.safe_output

        assert decision.status == "blocked"
        assert decision.selected_rule_id == "CLR-D003"
        assert output.startswith("Blocked:")
        assert "Primary reason:" in output
        assert "claim safety:" in output
        assert "Evidence checked:" in output
        assert "Operator action:" in output
        assert "Safe next step:" in output
        assert "claim_rejected" not in output
        assert "safe_rewrite" not in output
        assert "operator_review_required" not in output
        assert "channel_constraint" not in output
        assert "cta_softened" not in output
        assert len(output) >= 230


def test_a8_r104_2_margin_and_generic_blocks_have_specific_operator_actions() -> None:
    decisions = _decisions()

    kitchen = decisions["R105-CASE-003"]
    led = decisions["R105-CASE-005"]

    assert kitchen.status == "blocked"
    assert kitchen.selected_rule_id == "OFF-D002"
    assert "offer economics:" in kitchen.safe_output
    assert "margin" in kitchen.safe_output.lower()
    assert "broad discount" in kitchen.safe_output.lower()

    assert led.status == "blocked"
    assert led.selected_rule_id == "AGR-D001"
    assert "generic positioning:" in led.safe_output
    assert "category-only" in led.safe_output
    assert "specific product fact" in led.safe_output


def test_a8_r104_2_decision_identity_unchanged_from_r104_1() -> None:
    decisions = _decisions()
    observed = {
        case_id: (decision.status, decision.selected_rule_id)
        for case_id, decision in decisions.items()
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


def test_a8_r104_2_category_angle_wrapper_still_returns_legacy_tuple() -> None:
    output = category_angle_from_methodology("travel bottle")

    assert isinstance(output, tuple)
    assert len(output) == 3
    assert all(isinstance(item, str) for item in output)
    assert any("travel bottle" in item for item in output)


def test_a8_r104_2_engine_has_no_live_network_or_spend_paths() -> None:
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