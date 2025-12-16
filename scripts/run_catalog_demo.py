from __future__ import annotations

import sys
from pathlib import Path

# --- Bootstrap para que Python vea el root del proyecto ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ahora sí podemos importar los módulos del proyecto
from ops.catalog_pipeline import evaluate_catalog
from ops.capital_shield import CapitalShield


def main() -> None:
    """
    Demo del pipeline de catálogo:

    - Lee data/catalog/demo_catalog.csv
    - Ejecuta evaluate_catalog (Buyer + Quality + CapitalShield)
    - Imprime un resumen + RANKING por score
    """

    catalog_path = Path("data/catalog/candidates_real.csv")


    results, summary = evaluate_catalog(
        catalog_path=catalog_path,
        total_test_budget=100.0,
        capital_shield=CapitalShield(),
    )

    # === RESUMEN GENERAL ===
    print("\n=== RESUMEN DEL CATALOGO ===")
    print(f"Total productos      : {summary.total_products}")
    print(f"Aprobados (test)     : {summary.approved}")
    print(f"Rechazados           : {summary.rejected}")
    # 👇 AQUÍ ESTABA EL PROBLEMA: es needs_review, no under_review
    print(f"En revisión          : {summary.needs_review}")
    print(f"Budget total (input) : 100.0")

    # === RANKING POR SCORE ===
    print("\n=== RANKING POR SCORE (composite + quality) ===")

    # Ordenamos: primero composite_score, luego quality_score
    ordered = sorted(
        results,
        key=lambda r: ((r.composite_score or 0.0), (r.quality_score or 0.0)),
        reverse=True,
    )

    for r in ordered:
        comp = r.composite_score if r.composite_score is not None else 0.0
        qual = r.quality_score if r.quality_score is not None else 0.0
        print(
            f"- {r.product_id:>4} | dec={r.final_decision:9} "
            f"| comp={comp:5.2f} | qual={qual:5.2f} "
            f"| budget={r.allocated_test_budget:6.2f} "
            f"| reason={r.capital_reason}"
        )


if __name__ == "__main__":
    main()
