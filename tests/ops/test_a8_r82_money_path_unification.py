from __future__ import annotations

from decimal import Decimal

from ops.catalog_pipeline import evaluate_catalog, load_catalog_csv
from synapse.product_evaluator import evaluate_product


def test_product_evaluator_uses_decimal_financial_authority_for_approval():
    decision, record, quality = evaluate_product(
        {
            "product_id": "prod-pass",
            "name": "Healthy Margin Product",
            "price": "999.00",
            "cost": "260.00",
            "shipping_cost": "0.00",
            "estimated_cac": "180.00",
            "supplier_rating": "5.0",
            "reviews_count": "250",
        }
    )

    assert decision == "approved"
    assert record["final_decision"] == "approved"
    assert record["financial_decision"] == "PASS"
    assert "PASS_HEALTHY_UNIT_ECONOMICS" in record["financial_reason_codes"]
    assert record["financial_base"]["gross_margin_pct"] == "0.7397"
    assert quality.global_score >= 70.0


def test_product_evaluator_rejects_old_float_approval_case_when_decimal_engine_fails():
    decision, record, _quality = evaluate_product(
        {
            "product_id": "old-float-pass",
            "name": "Old Float Pass",
            "price": "100.00",
            "cost": "60.00",
            "shipping_cost": "0.00",
            "estimated_cac": "0.00",
            "supplier_rating": "5.0",
            "reviews_count": "100",
        }
    )

    assert decision == "rejected"
    assert record["final_decision"] == "rejected"
    assert record["financial_decision"] == "FAIL"
    assert "FAIL_MARGIN_BELOW_WATCH_THRESHOLD" in record["financial_reason_codes"]


def test_product_evaluator_fails_closed_when_required_financial_input_is_missing():
    decision, record, quality = evaluate_product(
        {
            "product_id": "missing-cac",
            "name": "Missing CAC Product",
            "price": "999.00",
            "cost": "260.00",
            "shipping_cost": "0.00",
            "supplier_rating": "5.0",
            "reviews_count": "250",
        }
    )

    assert decision == "rejected"
    assert record["final_decision"] == "rejected"
    assert record["financial_decision"] == "FAIL"
    assert record["financial_reason_codes"] == ["INVALID_FINANCIAL_INPUT"]
    assert "estimated_cac" in record["financial_error"]
    assert quality.global_score == 0.0


def test_catalog_pipeline_allocates_budget_from_decimal_financial_decision():
    results, summary = evaluate_catalog(
        products=[
            {
                "product_id": "prod-pass",
                "name": "Healthy Margin Product",
                "price": "999.00",
                "cost": "260.00",
                "shipping_cost": "0.00",
                "estimated_cac": "180.00",
                "supplier_rating": "5.0",
                "reviews_count": "250",
            },
            {
                "product_id": "prod-fail",
                "name": "Weak Margin Product",
                "price": "100.00",
                "cost": "60.00",
                "shipping_cost": "0.00",
                "estimated_cac": "0.00",
                "supplier_rating": "5.0",
                "reviews_count": "100",
            },
        ],
        total_test_budget=Decimal("200.00"),
    )

    by_id = {item.product_id: item for item in results}

    assert summary.total_products == 2
    assert summary.approved == 1
    assert summary.rejected == 1
    assert by_id["prod-pass"].final_decision == "approved"
    assert by_id["prod-pass"].allocated_test_budget == Decimal("200.00")
    assert by_id["prod-pass"].capital_reason == "approved"
    assert by_id["prod-fail"].final_decision == "rejected"
    assert by_id["prod-fail"].allocated_test_budget == Decimal("0.00")


def test_catalog_csv_parses_money_as_decimal(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "product_id,name,price,cost,shipping_cost,estimated_cac,supplier_rating,reviews_count,has_video,images_count\n"
        "p1,Product 1,999.00,260.00,15.50,180.00,4.8,120,true,3\n",
        encoding="utf-8",
    )

    products = load_catalog_csv(path)

    assert products[0]["price"] == Decimal("999.00")
    assert products[0]["cost"] == Decimal("260.00")
    assert products[0]["shipping_cost"] == Decimal("15.50")
    assert products[0]["estimated_cac"] == Decimal("180.00")
    assert products[0]["supplier_rating"] == 4.8
    assert products[0]["reviews_count"] == 120
    assert products[0]["has_video"] is True