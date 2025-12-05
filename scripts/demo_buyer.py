# scripts/demo_buyer.py

from __future__ import annotations

from buyer.schemas import ProductSchema, ProductSource
from synapse.product_evaluator import evaluate_product_with_quality


def make_good_product() -> ProductSchema:
    return ProductSchema(
        product_id="good_123",
        external_id="ext_123",
        name="Good Product",
        category="Electronics",
        cost_price=100.0,
        sale_price=200.0,  # 50% margin
        trust_score=9.0,
        source=ProductSource.CSV,
    )


def make_bad_product() -> ProductSchema:
    return ProductSchema(
        product_id="bad_123",
        external_id="ext_123",
        name="Bad Product",
        category="Electronics",
        cost_price=100.0,
        sale_price=110.0,  # 9% margin
        trust_score=9.0,
        source=ProductSource.CSV,
    )


def main() -> None:
    good_product = make_good_product()
    bad_product = make_bad_product()

    print("=== GOOD PRODUCT (Buyer + Quality + Bitácora) ===")
    good_record, good_quality = evaluate_product_with_quality(good_product)
    print("Final decision:", good_record["final_decision"])
    print("Record:", good_record)
    print("Quality:", {
        "global_passed": good_quality.global_passed,
        "global_score": good_quality.global_score,
        "lock_level": good_quality.lock_level.value,
        "hard_failures": good_quality.hard_failures,
        "soft_warnings": good_quality.soft_warnings,
    })
    print()

    print("=== BAD PRODUCT (Buyer + Quality + Bitácora) ===")
    bad_record, bad_quality = evaluate_product_with_quality(bad_product)
    print("Final decision:", bad_record["final_decision"])
    print("Record:", bad_record)
    print("Quality:", {
        "global_passed": bad_quality.global_passed,
        "global_score": bad_quality.global_score,
        "lock_level": bad_quality.lock_level.value,
        "hard_failures": bad_quality.hard_failures,
        "soft_warnings": bad_quality.soft_warnings,
    })
    print()

    print("[SYNAPSE] Demo Buyer + Quality + Bitácora completada ✅")


if __name__ == "__main__":
    main()
