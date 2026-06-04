# tests/marketing_os/test_brief_builder.py
"""A8-R66 tests for structured Marketing OS brief builder."""

from __future__ import annotations

import json

from synapse.marketing_os.brief_builder import (
    build_marketing_brief,
    build_marketing_brief_dict,
)
from synapse.marketing_os.brief_schema import SCHEMA_VERSION, MarketingBrief


def _product() -> dict:
    return {
        "product_id": "KC01_GOOD_MARGIN_SAFE_CLAIM",
        "name": "Masajeador Cervical Inteligente TENS",
        "category": "Salud/Bienestar/Gadgets ergonomicos",
        "price": 849.0,
        "cost": 230.0,
        "description": "Dispositivo de bienestar para pausas durante jornadas largas frente a pantalla.",
        "target_audience": "Estudiantes, programadores, emprendedores y oficinistas en MX con jornadas largas frente a pantalla.",
        "unique_features": ["compresa termica", "modo TENS", "uso portatil"],
        "known_objections": ["No se si lo voy a usar", "No quiero claims medicos"],
    }


def _decision() -> dict:
    return {
        "score": 0.82,
        "threshold": 0.70,
        "final_outcome": "GO",
        "permission_gate": "ALLOW",
        "reasons": ["margin_ok", "safe_claim_required"],
    }


def test_build_marketing_brief_returns_schema_object():
    brief = build_marketing_brief(_product(), _decision())

    assert isinstance(brief, MarketingBrief)
    assert brief.schema_version == SCHEMA_VERSION
    assert brief.product_id == "KC01_GOOD_MARGIN_SAFE_CLAIM"
    assert brief.product_name == "Masajeador Cervical Inteligente TENS"


def test_brief_contract_has_required_components():
    brief = build_marketing_brief(_product(), _decision())
    valid, issues = brief.validate_contract()

    assert valid is True
    assert issues == ()
    assert len(brief.pain_points) >= 3
    assert len(brief.objections) >= 3
    assert len(brief.hooks) >= 4
    assert len(brief.scripts) >= 2
    assert len(brief.ctas) >= 2


def test_brief_dict_is_json_ready_and_deterministic():
    first = build_marketing_brief_dict(_product(), _decision())
    second = build_marketing_brief_dict(_product(), _decision())

    assert first == second
    assert json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert first["brief_id"] == second["brief_id"]


def test_brief_has_claim_safety_notes_for_wellness_products():
    brief = build_marketing_brief(_product(), _decision())
    safety = brief.claims_safety_notes

    assert safety.posture == "restricted_wellness_claims"
    assert len(safety.notes) >= 3
    assert "tens" in safety.detected_risk_terms


def test_anti_npc_checks_pass_against_canonical_blacklist():
    brief = build_marketing_brief(_product(), _decision())

    assert brief.anti_npc_checks.passed is True
    assert brief.anti_npc_checks.banned_matches == ()
    assert len(brief.anti_npc_checks.checked_sections) >= 8


def test_blocked_decision_keeps_brief_but_marks_permission():
    decision = {
        "score": 0.31,
        "threshold": 0.70,
        "final_outcome": "BLOCK",
        "permission_gate": "DENY",
        "reasons": ["unsafe_claim", "margin_fail"],
    }

    brief = build_marketing_brief(_product(), decision)
    valid, issues = brief.validate_contract()

    assert valid is True
    assert issues == ()
    assert brief.permission.status == "blocked"
    assert brief.blocked_reasoning == ("unsafe_claim", "margin_fail")


def test_review_required_decision_has_blocked_reasoning():
    decision = {
        "score": 0.64,
        "threshold": 0.70,
        "final_outcome": "HOLD",
        "permission_gate": "REVIEW",
    }

    brief = build_marketing_brief(_product(), decision)

    assert brief.permission.status == "review_required"
    assert len(brief.blocked_reasoning) >= 1


def test_builder_accepts_object_with_to_dict():
    class ProductLike:
        product_id = "OBJ-1"
        name = "Barra de Luz LED Asimetrica"
        category = "Perifericos/Productividad"
        price = 949.0
        cost = 310.0
        target_audience = "Personas que trabajan de noche frente a monitor."
        unique_features = ["iluminacion asimetrica"]

        def to_dict(self):
            return {
                "product_id": self.product_id,
                "name": self.name,
                "category": self.category,
                "price": self.price,
                "cost": self.cost,
            }

    brief = build_marketing_brief(ProductLike(), {"final_outcome": "GO"})

    assert brief.product_id == "OBJ-1"
    assert "Barra de Luz" in brief.product_name
    assert brief.permission.status == "allowed"