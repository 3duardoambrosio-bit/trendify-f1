from __future__ import annotations

from synapse.product_evaluator import evaluate_product


def main() -> None:
    good_product = {
        "product_id": "good_123",
        "price": 100.0,
        "cost": 50.0,
        "supplier_rating": 4.8,
        "has_image": True,
        "name": "Good Product",
    }

    bad_product = {
        "product_id": "bad_123",
        "price": 100.0,
        "cost": 91.0,
        "supplier_rating": 4.8,
        "has_image": True,
        "name": "Bad Margin Product",
    }

    print("=== GOOD PRODUCT (Buyer + Quality + Bitácora) ===")
    final_decision_g, record_g, quality_g = evaluate_product(good_product)
    print("Final decision:", final_decision_g)
    print("Record:", record_g)
    print(
        "Quality:",
        {
            "global_passed": quality_g.global_passed,
            "global_score": quality_g.global_score,
            "lock_level": quality_g.lock_level.value,
            "hard_failures": quality_g.hard_failures,
            "soft_warnings": quality_g.soft_warnings,
        },
    )
    print()

    print("=== BAD PRODUCT (Buyer + Quality + Bitácora) ===")
    final_decision_b, record_b, quality_b = evaluate_product(bad_product)
    print("Final decision:", final_decision_b)
    print("Record:", record_b)
    print(
        "Quality:",
        {
            "global_passed": quality_b.global_passed,
            "global_score": quality_b.global_score,
            "lock_level": quality_b.lock_level.value,
            "hard_failures": quality_b.hard_failures,
            "soft_warnings": quality_b.soft_warnings,
        },
    )
    print()

    print("[SYNAPSE] Demo Buyer + Quality + Bitácora completada ✅")


if __name__ == "__main__":
    main()
