from typing import List

from ops.catalog_pipeline import (
    CatalogItemResult,
    load_catalog_csv,
    evaluate_catalog,
)
from ops.systems.autopilot import build_action_plan, summarize_action_plan


def main() -> None:
    """
    Demo del Autopilot sobre el catálogo demo/real.
    Reutiliza el pipeline de catálogo y encima arma el plan de acción.
    """
    from pathlib import Path

    real_path = Path("data/catalog/real_catalog.csv")
    if real_path.exists():
        path = real_path
    else:
        path = Path("data/catalog/demo_catalog.csv")

    print("=== AUTOPILOT DEMO (F1 STACK) ===\n")
    print(f"[INFO] Catálogo fuente   : {path}")

    products = load_catalog_csv(path)
    print(f"[INFO] Productos leídos  : {len(products)}")

    results: List[CatalogItemResult] = evaluate_catalog(
        products=products,
        total_test_budget=300.0,
    )

    plan = build_action_plan(results)
    summary = summarize_action_plan(plan)

    print("\n=== PLAN DE ACCIÓN POR PRODUCTO ===\n")
    for item in plan:
        print(f"- product_id : {item.product_id}")
        print(f"  action     : {item.action}")
        print(f"  reason     : {item.reason}")
        print(f"  test_budget: {item.test_budget:.2f}")
        print()

    print("=== RESUMEN DEL PLAN ===\n")
    print(f"Total productos     : {summary.total_products}")
    print(f"Para testear        : {summary.to_launch}")
    print(f"Para descartar      : {summary.to_skip}")
    print(f"Para revisar manual : {summary.to_review}")
    print(f"Budget de test total: {summary.total_test_budget:.2f}")

    print("\n[SYNAPSE] Autopilot F1 demo completada ✅")


if __name__ == "__main__":
    main()
