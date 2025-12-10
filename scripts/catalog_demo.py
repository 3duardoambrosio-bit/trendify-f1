# scripts/catalog_demo.py (solo este fragmento)

from pathlib import Path
from typing import List

from ops.catalog_pipeline import (
    load_catalog_csv,
    evaluate_catalog,
    summarize_catalog,
    CatalogItemResult,
)

def main() -> None:
    # Usa el catálogo "real" si existe, si no, cae al demo
    real_path = Path("data/catalog/real_catalog.csv")
    if real_path.exists():
        path = real_path
    else:
        path = Path("data/catalog/demo_catalog.csv")

    print("=== CATALOG PIPELINE DEMO ===\n")
    print(f"[INFO] Catalogo cargado desde: {path}")
    products = load_catalog_csv(path)
    print(f"[INFO] Productos leídos     : {len(products)}\n")

    results: List[CatalogItemResult] = evaluate_catalog(
        products,
        total_test_budget=300.0,
    )

    summary = summarize_catalog(results)

    # ... (resto igual como ya lo tienes)
