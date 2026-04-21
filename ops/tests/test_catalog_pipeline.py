from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Tuple

from infra.bitacora_auto import BitacoraAuto
from ops.catalog_pipeline import (
    CatalogItemResult,
    evaluate_catalog,
    load_catalog_csv,
    summarize_catalog,
)
from synapse.quality_gate import QualityResult

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


def test_evaluate_catalog_uses_evaluator_and_capital_shield(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """El pipeline debe usar evaluate_product y asignar budget sólo a aprobados."""

    # Import local para poder hacer monkeypatch sin conflictos
    from synapse import product_evaluator

    def fake_eval(product: Dict[str, Any]) -> Tuple[str, Dict[str, Any], QualityResult]:
        """Simula evaluate_product para controlar las decisiones del pipeline."""
        pid = product["product_id"]

        if pid == "p1":
            buyer_decision = "approved"
            record: Dict[str, Any] = {
                "product_id": pid,
                "buyer_decision": "approved",
                "buyer_scores": {"composite_score": 0.8},
                "quality_score": 0.9,  # 👈 antes era quality_global_score
                "final_decision": "approved",
            }
        else:
            buyer_decision = "rejected"
            record = {
                "product_id": pid,
                "buyer_decision": "rejected",
                "buyer_scores": {"composite_score": 0.3},
                "quality_score": 0.4,  # 👈 antes era quality_global_score
                "final_decision": "rejected",
            }

        quality = QualityResult(global_score=record["quality_score"])
        return buyer_decision, record, quality

    # El pipeline debe usar nuestro fake_eval
    monkeypatch.setattr(product_evaluator, "evaluate_product", fake_eval)

    # Preparamos un CSV chiquito en tmp_path
    catalog_path = tmp_path / "demo_catalog.csv"
    catalog_path.write_text(
        "product_id,name,cost,price,shipping_cost,supplier_rating,reviews_count\n"
        "p1,Prod 1,10,30,0,4.5,100\n"
        "p2,Prod 2,10,30,0,4.5,100\n",
        encoding="utf-8",
    )

    # Ejecutamos el pipeline real
    results, summary = evaluate_catalog(
        catalog_path=catalog_path,
        total_test_budget=100.0,
        capital_shield=None,
    )

    # Sólo p1 debería tener presupuesto asignado
    assert len(results) == 2

    approved = [r for r in results if r.final_decision == "approved"]
    rejected = [r for r in results if r.final_decision == "rejected"]

    assert len(approved) == 1
    assert approved[0].product_id == "p1"
    assert approved[0].allocated_test_budget > 0

    assert len(rejected) == 1
    assert rejected[0].allocated_test_budget == 0
    # summary se usa sólo para validar que no truene
    assert summary.total_products == 2



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

def test_evaluate_catalog_respects_capital_shield_when_provided(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from synapse import product_evaluator

    class FakeDecision:
        def __init__(self, allocated: Decimal, reason: str) -> None:
            self.allocated = allocated
            self.reason = reason

    class FakeShield:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Decimal]] = []

        def decide_for_product(self, *, final_decision: str, requested_amount: Decimal) -> FakeDecision:
            amt = Decimal(str(requested_amount))
            self.calls.append((final_decision, amt))
            return FakeDecision(allocated=Decimal("0"), reason="insufficient_budget")

    def fake_eval(product: Dict[str, Any]) -> Tuple[str, Dict[str, Any], QualityResult]:
        pid = product["product_id"]

        if pid == "p1":
            buyer_decision = "approved"
            record: Dict[str, Any] = {
                "product_id": pid,
                "buyer_decision": "approved",
                "buyer_scores": {"composite_score": 0.8},
                "quality_score": 0.9,
                "final_decision": "approved",
            }
        else:
            buyer_decision = "rejected"
            record = {
                "product_id": pid,
                "buyer_decision": "rejected",
                "buyer_scores": {"composite_score": 0.3},
                "quality_score": 0.4,
                "final_decision": "rejected",
            }

        quality = QualityResult(global_score=record["quality_score"])
        return buyer_decision, record, quality

    monkeypatch.setattr(product_evaluator, "evaluate_product", fake_eval)

    catalog_path = tmp_path / "demo_catalog.csv"
    catalog_path.write_text(
        "product_id,name,cost,price,shipping_cost,supplier_rating,reviews_count\n"
        "p1,Prod 1,10,30,0,4.5,100\n"
        "p2,Prod 2,10,30,0,4.5,100\n",
        encoding="utf-8",
    )

    shield = FakeShield()

    results, summary = evaluate_catalog(
        catalog_path=catalog_path,
        total_test_budget=100.0,
        capital_shield=shield,
    )

    approved = [r for r in results if r.final_decision == "approved"]
    rejected = [r for r in results if r.final_decision == "rejected"]

    assert len(approved) == 1
    assert len(rejected) == 1
    assert len(shield.calls) == 1

    assert shield.calls[0][0] == "approved"
    assert shield.calls[0][1] > Decimal("0")

    assert approved[0].product_id == "p1"
    assert approved[0].allocated_test_budget == 0.0
    assert approved[0].capital_reason == "insufficient_budget"

    assert rejected[0].product_id == "p2"
    assert rejected[0].allocated_test_budget == 0.0
    assert rejected[0].capital_reason == "not_approved"

    assert summary.total_products == 2
    assert summary.approved == 1

