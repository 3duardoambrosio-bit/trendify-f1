from pathlib import Path
from typing import Any, Dict, List

from infra.bitacora_auto import BitacoraAuto
from ops.catalog_pipeline import (
    CatalogItemResult,
    evaluate_catalog,
    load_catalog_csv,
    summarize_catalog,
)
from synapse import product_evaluator


def test_load_catalog_csv_parses_rows(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(
        "product_id,price,cost,shipping_cost,supplier_rating,reviews_count,delivery_time_days,has_video,images_count\n"
        "p1,100,40,0,4.5,120,7,true,4\n"
        "p2,50,25,5,4.0,80,10,false,2\n",
        encoding="utf-8",
    )

    products = load_catalog_csv(path)
    assert len(products) == 2
    assert products[0]["product_id"] == "p1"
    assert products[0]["price"] == 100.0
    assert products[0]["has_video"] is True
    assert products[1]["has_video"] is False


def test_evaluate_catalog_uses_evaluator_and_capital_shield(monkeypatch, tmp_path: Path) -> None:
    """El pipeline debe usar evaluate_product y asignar budget sólo a aprobados."""

    def fake_eval(product: Dict[str, Any], bitacora: BitacoraAuto):
        pid = product["product_id"]
        if pid == "good":
            final_decision = "approved"
            record = {
                "product_id": pid,
                "buyer_decision": "approved",
                "buyer_scores": {"composite_score": 0.8},
                "quality_global_score": 0.9,
                "final_decision": "approved",
            }
        else:
            final_decision = "rejected"
            record = {
                "product_id": pid,
                "buyer_decision": "rejected",
                "buyer_scores": {"composite_score": 0.3},
                "quality_global_score": 0.4,
                "final_decision": "rejected",
            }

        class Quality:
            def __init__(self, score: float) -> None:
                self.global_score = score

        quality = Quality(record["quality_global_score"])
        return final_decision, record, quality

    monkeypatch.setattr(product_evaluator, "evaluate_product", fake_eval)

    products: List[Dict[str, Any]] = [
        {"product_id": "good"},
        {"product_id": "bad"},
    ]

    bitacora = BitacoraAuto(path=tmp_path / "bitacora.jsonl")
    results = evaluate_catalog(products, total_test_budget=100.0, bitacora=bitacora)

    assert len(results) == 2

    good = next(r for r in results if r.product_id == "good")
    bad = next(r for r in results if r.product_id == "bad")

    assert good.final_decision == "approved"
    assert good.allocated_test_budget > 0
    assert bad.final_decision == "rejected"
    assert bad.allocated_test_budget == 0.0


def test_summarize_catalog_counts_decisions() -> None:
    items = [
        CatalogItemResult(
            product_id="p1",
            final_decision="approved",
            buyer_decision="approved",
            composite_score=0.8,
            quality_score=0.9,
            allocated_test_budget=10.0,
            capital_reason="ok",
        ),
        CatalogItemResult(
            product_id="p2",
            final_decision="rejected",
            buyer_decision="rejected",
            composite_score=0.2,
            quality_score=0.5,
            allocated_test_budget=0.0,
            capital_reason="not_approved",
        ),
        CatalogItemResult(
            product_id="p3",
            final_decision="unknown",
            buyer_decision=None,
            composite_score=None,
            quality_score=None,
            allocated_test_budget=0.0,
            capital_reason="not_evaluated",
        ),
    ]

    summary = summarize_catalog(items)
    assert summary.total_products == 3
    assert summary.approved == 1
    assert summary.rejected == 1
    assert summary.unknown == 1
