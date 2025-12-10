# scripts/catalog_demo.py

from __future__ import annotations

from pathlib import Path
from typing import List

from infra.bitacora_auto import BitacoraAuto
from ops.catalog_pipeline import (
    CATALOG_PATH,
    CatalogItemResult,
    load_catalog_csv,
    evaluate_catalog,
    summarize_catalog,
)


def _print_item(item: CatalogItemResult) -> None:
    print(f"- product_id   : {item.product_id}")
    print(f"  decision     : {item.final_decision}")
    print(f"  buyer_dec    : {item.buyer_decision}")
    print(f"  comp_score   : {item.composite_score}")
    print(f"  quality      : {item.quality_score}")
    print(f"  test_budget  : {item.allocated_test_budget:.2f}")
    print(f"  capital_note : {item.capital_reason}")
    print()


def main() -> None:
    print("=== CATALOG PIPELINE DEMO ===\n")

    path: Path = CATALOG_PATH

    if not path.exists():
        print(f"[ERROR] No se encontró el catálogo en: {path}")
        print("Crea el archivo y vuelve a correr el demo.")
        return

    products = load_catalog_csv(path)
    if not products:
        print(f"[WARN] El catálogo en {path} está vacío.")
        return

    print(f"[INFO] Catalogo cargado desde: {path}")
    print(f"[INFO] Productos leídos     : {len(products)}\n")

    # Bitácora específica para este demo (usa el path por defecto)
    bitacora = BitacoraAuto()

    # Supongamos que tienes un budget total de prueba de 100 USD
    total_test_budget: float = 100.0

    results: List[CatalogItemResult] = evaluate_catalog(
        products=products,
        total_test_budget=total_test_budget,
        bitacora=bitacora,
    )

    print("=== RESULTADOS POR PRODUCTO ===\n")
    for item in results:
        _print_item(item)

    summary = summarize_catalog(results)

    print("=== RESUMEN DEL CATÁLOGO ===\n")
    print(f"Total productos     : {summary.total_products}")
    print(f"Aprobados           : {summary.approved}")
    print(f"Rechazados          : {summary.rejected}")
    print(f"Unknown             : {summary.unknown}")
    print(f"Test budget total   : {summary.total_test_budget:.2f}")
    print(f"Avg composite score : {summary.avg_composite_score:.3f}")
    print(f"Avg quality score   : {summary.avg_quality_score:.3f}")
    print("\n[SYNAPSE] Demo catálogo completada ✅")


if __name__ == "__main__":
    main()
