from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SOURCE_PATH = REPO / "tools" / "product_candidate_source.py"
ENGINE_PATH = REPO / "tools" / "product_decision_engine.py"


def load_module(name: str, path: Path):
    tools_path = str(REPO / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)

    spec = importlib.util.spec_from_file_location(name, path)
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


def test_candidate_source_normalizes_valid_rows_and_rejects_bad_rows():
    source = load_module("product_candidate_source", SOURCE_PATH)

    payload = {
        "source_name": "manual_research_sheet_export",
        "rows": [
            candidate(
                sku="WINNER-001",
                name=" Portable Airflow Gadget ",
                landed_cost=10,
                sell_price=39,
            ),
            candidate(sku="WINNER-001"),
            candidate(sku="BAD-MARGIN", landed_cost=20, sell_price=19),
            candidate(sku="BAD-SCORE", demand_score=120),
            candidate(sku="MANUAL-FLAG", selected=True),
            {"sku": "INCOMPLETE"},
        ],
    }

    result = source.normalize_candidate_source(payload, source_id="local_sheet_a")

    assert result["source_contract_version"] == "A8-R33.product-candidate-source.v1"
    assert result["source_id"] == "local_sheet_a"
    assert len(result["source_sha256"]) == 64
    assert result["manual_champion_provided"] is False
    assert result["selection_mode"] == "source_normalization_only"

    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["sku"] == "WINNER-001"
    assert result["candidates"][0]["name"] == "Portable Airflow Gadget"
    assert isinstance(result["candidates"][0]["landed_cost"], float)

    report = result["source_quality_report"]
    assert report["input_rows"] == 6
    assert report["valid_candidates"] == 1
    assert report["rejected_rows"] == 5
    assert report["duplicate_skus_blocked"] == 1
    assert report["manual_selection_markers_blocked"] == 1
    assert report["valid_ratio"] == 0.1667

    reasons = {item["reason"] for item in result["rejected_rows"]}
    assert "duplicate_sku" in reasons
    assert "sell_price_must_exceed_landed_cost" in reasons
    assert "demand_score_must_be_between_0_and_100" in reasons
    assert "manual_selection_key_forbidden:selected" in reasons


def test_candidate_source_blocks_top_level_manual_selection_keys():
    source = load_module("product_candidate_source", SOURCE_PATH)

    payload = {
        "selected_product": "SKU-1",
        "candidates": [candidate(sku="SKU-1")],
    }

    try:
        source.normalize_candidate_source(payload)
    except ValueError as exc:
        assert "manual_selection_key_forbidden:selected_product" in str(exc)
    else:
        raise AssertionError("top-level manual selection key must fail")


def test_candidate_source_output_feeds_product_decision_engine():
    source = load_module("product_candidate_source", SOURCE_PATH)
    engine = load_module("product_decision_engine", ENGINE_PATH)

    normalized = source.normalize_candidate_source(
        {
            "rows": [
                candidate(
                    sku="ORDER-TRAP",
                    demand_score=58.0,
                    content_fit_score=57.0,
                    supplier_score=72.0,
                ),
                candidate(
                    sku="REAL-WINNER",
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
                ),
            ]
        }
    )

    decision = engine.select_product_candidates(normalized["candidates"], backup_count=1)

    assert normalized["quality_gates"]["ready_for_product_decision_cli"] is True
    assert decision["selection_mode"] == "system_scored"
    assert decision["manual_selection_used"] is False
    assert decision["champion"]["sku"] == "REAL-WINNER"
    assert decision["backups"][0]["sku"] == "ORDER-TRAP"


def test_candidate_source_is_deterministic_for_same_input():
    source = load_module("product_candidate_source", SOURCE_PATH)

    payload = {"rows": [candidate(sku="A"), candidate(sku="B", demand_score=81.0)]}

    first = source.normalize_candidate_source(payload)
    second = source.normalize_candidate_source(payload)

    assert first == second


def test_candidate_source_rejects_invalid_payload_shapes():
    source = load_module("product_candidate_source", SOURCE_PATH)

    bad_payloads = [
        "not-object",
        {"candidates": "not-list"},
        {"rows": "not-list"},
        {"unknown": []},
        [],
    ]

    for payload in bad_payloads:
        try:
            source.normalize_candidate_source(payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"payload should fail: {payload!r}")


def test_candidate_source_has_no_network_or_dynamic_behavior_markers():
    source_text = SOURCE_PATH.read_text(encoding="utf-8")

    forbidden_markers = [
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "eval(",
        "exec(",
    ]

    found = [marker for marker in forbidden_markers if marker in source_text]
    assert found == []
