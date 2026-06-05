import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from synapse.discovery.synthetic_discovery import (
    generate_synthetic_candidates,
    normalize_synthetic_candidate,
)
from synapse.discovery.synthetic_schema import (
    DISCOVERY_SCHEMA_VERSION,
    DiscoverySignal,
    calculate_margin_pct,
    candidate_to_marketing_product,
    validate_candidate_contract,
)
from synapse.marketing_os.brief_builder import build_marketing_brief_dict


def _record(**overrides):
    base = {
        "product_name": "Organizador magnético para cocina",
        "category": "home_lifestyle",
        "market": "MX",
        "price": 500,
        "cost": 125,
        "traffic": 700,
        "days": 3,
        "marketing_angle": "orden visual en cocinas pequeñas",
        "primary_hook": "Convierte una pared vacía en espacio útil.",
        "target_audience": "personas con cocinas pequeñas que compran soluciones de orden online",
        "use_case": "ordenar utensilios visibles sin perforaciones complejas",
        "demand_signals": (
            {
                "name": "visual_before_after",
                "score": 0.82,
                "rationale": "El contraste antes/después se demuestra sin exagerar.",
                "kind": "demand",
            },
        ),
        "risk_signals": (
            {
                "name": "commodity_angle",
                "score": 0.27,
                "rationale": "Se vuelve genérico si sólo se vende como organizador barato.",
                "kind": "risk",
            },
        ),
        "differentiation_signals": (
            {
                "name": "small_space_anchor",
                "score": 0.79,
                "rationale": "La diferenciación se ancla en cocina pequeña y pared útil.",
                "kind": "differentiation",
            },
        ),
        "evidence_notes": (
            "Synthetic sandbox fixture.",
            "No platform read, write, scraping, inventory check, or spend.",
        ),
    }
    base.update(overrides)
    return base


def test_generate_synthetic_candidates_is_deterministic_and_sorted():
    first = [candidate.to_dict() for candidate in generate_synthetic_candidates()]
    second = [candidate.to_dict() for candidate in generate_synthetic_candidates()]

    assert first == second
    assert len(first) == 3

    ids = [candidate["candidate_id"] for candidate in first]
    assert ids == sorted(ids)
    assert len(set(ids)) == 3


def test_candidate_contract_is_json_ready_and_contains_required_fields():
    candidate = generate_synthetic_candidates()[0]
    payload = candidate.to_dict()

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["candidate_id"] == candidate.candidate_id
    assert decoded["product_id"] == candidate.candidate_id
    assert decoded["source_type"] == "synthetic"
    assert decoded["created_by_version"] == DISCOVERY_SCHEMA_VERSION
    assert decoded["price"] > decoded["cost"]
    assert decoded["gross_margin_mxn"] == decoded["price"] - decoded["cost"]
    assert decoded["margin_pct"] == calculate_margin_pct(decoded["price"], decoded["cost"])
    assert len(decoded["demand_signals"]) >= 1
    assert len(decoded["risk_signals"]) >= 1
    assert len(decoded["differentiation_signals"]) >= 1
    assert len(decoded["evidence_notes"]) >= 1
    assert validate_candidate_contract(candidate) == ()


def test_margin_calculation_uses_price_as_denominator():
    candidate = normalize_synthetic_candidate(_record(price=1000, cost=250))

    assert candidate.gross_margin_mxn == 750
    assert candidate.margin_pct == 0.75
    assert candidate.to_dict()["proposed_price_mxn"] == 1000
    assert candidate.to_dict()["estimated_landed_cost_mxn"] == 250


def test_candidate_is_frozen():
    candidate = normalize_synthetic_candidate(_record())

    with pytest.raises(FrozenInstanceError):
        candidate.product_name = "Mutación prohibida"


def test_invalid_candidate_rejects_negative_margin_before_pipeline_use():
    with pytest.raises(ValueError, match="INVALID_SYNTHETIC_CANDIDATE"):
        normalize_synthetic_candidate(_record(price=100, cost=120))


def test_invalid_signal_score_is_rejected():
    with pytest.raises(ValueError, match="score must be between 0 and 1"):
        DiscoverySignal(name="bad", score=1.5, rationale="out of range", kind="demand")


def test_marketing_brief_builder_accepts_candidate_mapping():
    candidate = normalize_synthetic_candidate(_record())
    product = candidate_to_marketing_product(candidate)

    brief = build_marketing_brief_dict(
        product,
        {
            "permission_gate": "ALLOW",
            "final_outcome": "TEST_SMALL_BUDGET_SANDBOX",
            "reason": "Synthetic discovery candidate cleared local contract gates.",
        },
    )

    assert brief["product_id"] == candidate.candidate_id
    assert brief["product_name"] == candidate.product_name
    assert brief["audience"]
    assert brief["core_angle"]

    permission = brief["permission"]
    assert isinstance(permission, dict)
    assert sorted(permission.keys()) == ["reasons", "score", "status", "threshold"]
    assert permission["status"] == "allowed"
    assert permission["reasons"] == ["Synthetic discovery candidate cleared local contract gates."]
    assert permission["score"] is None
    assert permission["threshold"] is None

    assert "anti_npc_checks" in brief
    assert "claims_safety_notes" in brief


def test_static_forbidden_terms_absent_from_new_discovery_modules():
    root = Path(__file__).resolve().parents[2]
    target_files = (
        root / "synapse" / "discovery" / "synthetic_schema.py",
        root / "synapse" / "discovery" / "synthetic_discovery.py",
    )

    forbidden_terms = (
        "requests.",
        "httpx.",
        "urllib.request",
        "aiohttp",
        "selenium",
        "playwright",
        "BeautifulSoup",
        "subprocess",
        "os.system",
        "socket.",
        "shopify",
        "dropi",
        "facebook",
    )

    for path in target_files:
        text = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in text, f"{term} found in {path}"