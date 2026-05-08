from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "tools" / "product_decision_engine.py"


def load_engine():
    spec = importlib.util.spec_from_file_location("product_decision_engine", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def candidate(**overrides):
    base = {
        "sku": "BASE-001",
        "name": "Base Candidate",
        "niche": "tech_gadgets",
        "landed_cost": 12.0,
        "sell_price": 34.0,
        "shipping_days": 7.0,
        "supplier_score": 82.0,
        "demand_score": 72.0,
        "saturation_score": 48.0,
        "content_fit_score": 76.0,
        "problem_severity_score": 64.0,
        "compliance_risk_score": 12.0,
        "return_risk_score": 22.0,
    }
    base.update(overrides)
    return base


def test_product_decision_engine_selects_champion_by_score_not_manual_order():
    engine = load_engine()

    first_but_weaker = candidate(
        sku="FIRST-WEAKER",
        name="First But Weaker",
        demand_score=58.0,
        content_fit_score=56.0,
        problem_severity_score=52.0,
        supplier_score=72.0,
    )

    actual_champion = candidate(
        sku="AIR-COOL-PRO",
        name="Portable Airflow Gadget",
        landed_cost=10.0,
        sell_price=39.0,
        shipping_days=5.0,
        supplier_score=91.0,
        demand_score=88.0,
        saturation_score=31.0,
        content_fit_score=93.0,
        problem_severity_score=84.0,
        compliance_risk_score=8.0,
        return_risk_score=16.0,
    )

    valid_backup = candidate(
        sku="DESK-LIGHT-SMART",
        name="Smart Desk Light",
        demand_score=78.0,
        content_fit_score=84.0,
        problem_severity_score=72.0,
        saturation_score=42.0,
    )

    result = engine.select_product_candidates(
        [first_but_weaker, actual_champion, valid_backup],
        backup_count=2,
    )

    assert result["selection_mode"] == "system_scored"
    assert result["manual_selection_used"] is False
    assert result["acceptance"]["manual_selection_blocked_as_primary_flow"] is True
    assert result["champion"]["sku"] == "AIR-COOL-PRO"
    assert result["champion"]["score"] > result["backups"][0]["score"]
    assert result["counts"] == {
        "input": 3,
        "passed": 3,
        "blocked": 0,
        "backups": 2,
    }


def test_product_decision_engine_blocks_bad_candidates_with_auditable_reasons():
    engine = load_engine()

    bad_margin = candidate(
        sku="BAD-MARGIN",
        landed_cost=19.0,
        sell_price=24.0,
    )

    bad_supplier = candidate(
        sku="BAD-SUPPLIER",
        supplier_score=44.0,
    )

    risky = candidate(
        sku="RISKY-COMPLIANCE",
        compliance_risk_score=61.0,
        return_risk_score=72.0,
    )

    result = engine.select_product_candidates([bad_margin, bad_supplier, risky])

    assert result["champion"] is None
    assert result["backups"] == []
    assert result["counts"]["input"] == 3
    assert result["counts"]["passed"] == 0
    assert result["counts"]["blocked"] == 3

    reasons_by_sku = {
        item["sku"]: set(item["block_reasons"])
        for item in result["rejected_candidates"]
    }

    assert "gross_margin_below_minimum" in reasons_by_sku["BAD-MARGIN"]
    assert "supplier_score_below_minimum" in reasons_by_sku["BAD-SUPPLIER"]
    assert "compliance_risk_score_above_maximum" in reasons_by_sku["RISKY-COMPLIANCE"]
    assert "return_risk_score_above_maximum" in reasons_by_sku["RISKY-COMPLIANCE"]


def test_product_decision_engine_outputs_explainable_numeric_contract():
    engine = load_engine()

    result = engine.select_product_candidates(
        [
            candidate(
                sku="CHAMPION-001",
                landed_cost=9.0,
                sell_price=36.0,
                supplier_score=90.0,
                demand_score=86.0,
                saturation_score=35.0,
                content_fit_score=91.0,
                problem_severity_score=83.0,
                compliance_risk_score=9.0,
                return_risk_score=18.0,
            )
        ]
    )

    champion = result["champion"]
    assert champion is not None
    assert champion["decision"] == "PASS"
    assert champion["gross_margin_pct"] >= 35.0
    assert 0.0 <= champion["score"] <= 100.0

    required_components = {
        "demand",
        "gross_margin",
        "content_fit",
        "problem_severity",
        "competition",
        "operational",
        "risk",
    }
    assert set(champion["score_components"]) == required_components

    for value in champion["score_components"].values():
        assert isinstance(value, float)
        assert 0.0 <= value <= 100.0

    assert result["acceptance"]["has_champion"] is True
    assert result["acceptance"]["champion_explainable"] is True


def test_product_decision_engine_is_deterministic_for_same_inputs():
    engine = load_engine()

    candidates = [
        candidate(sku="A", demand_score=70.0),
        candidate(sku="B", demand_score=82.0),
        candidate(sku="C", demand_score=77.0),
    ]

    first = engine.select_product_candidates(candidates)
    second = engine.select_product_candidates(candidates)

    assert first == second


def test_product_decision_engine_rejects_unknown_constraints_and_bad_weight_sum():
    engine = load_engine()

    valid = candidate()

    try:
        engine.select_product_candidates([valid], constraints={"unknown_constraint": 1.0})
    except ValueError as exc:
        assert "unknown constraint" in str(exc)
    else:
        raise AssertionError("unknown constraint must fail")

    try:
        engine.select_product_candidates([valid], weights={"demand": 0.99})
    except ValueError as exc:
        assert "weights must sum" in str(exc)
    else:
        raise AssertionError("bad weight sum must fail")


def test_product_decision_engine_has_no_network_random_or_manual_override_markers():
    source = MODULE_PATH.read_text(encoding="utf-8")

    forbidden_markers = [
        "requests",
        "httpx",
        "urllib",
        "socket",
        "random",
        "manual_override",
        "manual_pick",
        "operator_selected_champion",
    ]

    found = [marker for marker in forbidden_markers if marker in source]
    assert found == []
