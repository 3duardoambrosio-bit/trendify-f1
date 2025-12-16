from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

# Bootstrap de path para importar paquetes internos
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ops.catalog_pipeline import (
    load_catalog_csv,
    evaluate_catalog,
    summarize_catalog,
)


CANDIDATES_PATH = (
    Path(__file__)
    .resolve()
    .parent.parent
    / "data"
    / "catalog"
    / "candidates_demo.csv"
)


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _ensure_candidates_file_exists() -> None:
    """
    Si no existe el archivo de candidatos, crea una plantilla mínima
    para que el usuario la edite con productos reales.
    """
    if CANDIDATES_PATH.exists():
        return

    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)

    template = (
        "product_id,title,price,cost,shipping_cost,rating,reviews\n"
        "r001,Mouse inalámbrico gamer,19.99,6.50,3.00,4.6,314\n"
        "r002,Aro de luz LED 12\",24.99,7.20,4.00,4.4,189\n"
        "r003,Soporte ajustable para laptop,29.99,9.50,3.50,4.7,256\n"
    )

    CANDIDATES_PATH.write_text(template, encoding="utf-8")

    _print_header("PLANTILLA DE CANDIDATOS CREADA")
    print(f"Se creó un archivo de ejemplo en:\n  {CANDIDATES_PATH}")
    print(
        "\nEdita ese CSV con tus propios productos reales "
        "y vuelve a correr este comando:\n"
        "  python scripts\\run_candidates_demo.py"
    )


def _print_ranking(items: List[Any]) -> None:
    _print_header("RANKING DE CANDIDATOS POR SCORE (composite + quality)")

    # Ordenamos de mayor a menor composite_score
    sorted_items = sorted(
        items,
        key=lambda it: float(getattr(it, "composite_score", 0.0)),
        reverse=True,
    )

    for item in sorted_items:
        product_id = getattr(item, "product_id", "")
        title = getattr(item, "title", "") if hasattr(item, "title") else ""
        final_decision = getattr(item, "final_decision", "")
        comp = float(getattr(item, "composite_score", 0.0))
        qual = float(getattr(item, "quality_score", 0.0))
        budget = float(getattr(item, "allocated_test_budget", 0.0))
        capital_reason = getattr(item, "capital_reason", "")

        title_str = f" {title}" if title else ""
        print(
            f"- {product_id:>4}{title_str} | dec={final_decision:9} "
            f"| comp={comp:6.2f} | qual={qual:6.2f} "
            f"| budget={budget:6.2f} | reason={capital_reason}"
        )


def main() -> None:
    # 1) Crear plantilla si no existe
    _ensure_candidates_file_exists()

    if not CANDIDATES_PATH.exists():
        # Si por alguna razón sigue sin existir, abortamos limpio
        print("No se encontró el archivo de candidatos y no se pudo crear plantilla.")
        return

    # 2) Cargar candidatos reales desde el CSV
    _print_header("CANDIDATOS — CARGA DE CSV")
    print(f"Usando archivo:\n  {CANDIDATES_PATH}")

    catalog = load_catalog_csv(CANDIDATES_PATH)

    # 3) Evaluar catálogo con el pipeline actual
    items, summary = evaluate_catalog(
        catalog,
        total_test_budget=100.0,
    )

    _print_header("RESUMEN DE CANDIDATOS")
    print(f"Total productos      : {summary.total_products}")
    print(f"Aprobados            : {summary.approved}")
    print(f"Rechazados           : {summary.rejected}")
    print(f"En revisión          : {summary.needs_review}")

    total_budget = sum(
        float(getattr(item, "allocated_test_budget", 0.0)) for item in items
    )
    print(f"Budget total asignado: {total_budget:.2f}")

    # 4) Ranking detallado
    _print_ranking(items)


if __name__ == "__main__":
    main()
