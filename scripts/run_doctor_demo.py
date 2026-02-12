
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List
from synapse.infra.time_utc import now_utc, isoformat_z

# --- Bootstrap de path: asegurar que la raíz del proyecto esté en sys.path ---

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ahora sí, imports de paquetes internos
from ops.catalog_pipeline import (
    load_catalog_csv,
    evaluate_catalog,
    summarize_catalog,
)
from intelligence.factors import (
    analyze_success_factors,
    generate_insights,
)
from intelligence.early_warning import (
    generate_early_warning,
)


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _build_factor_rows(items: List[Any]) -> List[Dict[str, Any]]:
    """
    Transforma CatalogItemResult -> filas para factor analysis.

    No asumimos detalles internos raros, solo campos estándar que
    sabemos que existen por el demo:
    - product_id
    - final_decision
    - composite_score
    - quality_score
    - allocated_test_budget
    """
    rows: List[Dict[str, Any]] = []

    for item in items:
        composite = float(getattr(item, "composite_score", 0.0))
        quality = float(getattr(item, "quality_score", 0.0))
        budget = float(getattr(item, "allocated_test_budget", 0.0))
        final_decision = str(getattr(item, "final_decision", ""))

        rows.append(
            {
                "product_id": getattr(item, "product_id", ""),
                "was_successful": final_decision == "approved",
                "composite_score": composite,
                "quality_score": quality,
                "allocated_test_budget": budget,
            }
        )

    return rows


def _demo_factor_analysis(items: List[Any]) -> None:
    _print_header("FACTOR ANALYSIS — GANADORES VS PERDEDORES")

    rows = _build_factor_rows(items)

    analyses = analyze_success_factors(
        rows,
        success_field="was_successful",
        factors=[
            "composite_score",
            "quality_score",
            "allocated_test_budget",
        ],
    )

    insights = generate_insights(analyses)

    if not insights:
        print("Sin insights significativos (dataset muy simétrico o pequeño).")
        return

    for msg in insights:
        print("-", msg)


def _demo_early_warning() -> None:
    """
    Demo sintético de early-warning.

    Simulamos un ROAS que viene cayendo:
    1.8, 1.6, 1.4, 1.2, 0.9
    y preguntamos: ¿cuándo se cruza por debajo de 1.0?
    """
    _print_header("EARLY WARNING — ROAS SIMULADO")

    now = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    values = [1.8, 1.6, 1.4, 1.2, 0.9]

    series = [
        (now - timedelta(days=(len(values) - 1 - i)), v)
        for i, v in enumerate(values)
    ]

    signal = generate_early_warning(
        metric="roas",
        values=series,
        threshold=1.0,
        direction="below",
        max_horizon_days=7,
    )

    if signal is None:
        print("Sin señal de riesgo: a esta tendencia no parece cruzar el umbral.")
        return

    print(f"Nivel: {signal.level.upper()}")
    print(f"Mensaje: {signal.message}")
    print(f"Días estimados al umbral: {signal.days_to_threshold}")
    print(f"Valor actual: {signal.current_value:.2f}")


def main() -> None:
    # 1) Cargar catálogo demo y evaluarlo con el pipeline actual
    data_path = (
        Path(__file__)
        .resolve()
        .parent.parent
        / "data"
        / "catalog"
        / "demo_catalog.csv"
    )

    catalog = load_catalog_csv(data_path)

    # Mantengo la firma más estándar posible; si tu evaluate_catalog
    # tiene otros parámetros, lo ajustaríamos con el error real.
    items, summary = evaluate_catalog(
        catalog,
        total_test_budget=100.0,
    )

    # 2) Resumen del catálogo (igual que el demo normal)
    _print_header("RESUMEN DEL CATALOGO (DOCTOR DEMO)")
    print(f"Total productos      : {summary.total_products}")
    print(f"Aprobados            : {summary.approved}")
    print(f"Rechazados           : {summary.rejected}")
    print(f"En revisión          : {summary.needs_review}")

    # Budget total realmente asignado (sumando lo que ve el pipeline)
    total_allocated = sum(
        float(getattr(item, "allocated_test_budget", 0.0)) for item in items
    )
    print(f"Budget total (asignado) : {total_allocated:.2f}")

    # 3) Factor analysis sobre winners vs losers
    _demo_factor_analysis(items)

    # 4) Early-warning sintético de ROAS
    _demo_early_warning()


if __name__ == "__main__":
    main()
