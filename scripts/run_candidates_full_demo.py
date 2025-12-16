from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Bootstrap de path para importar paquetes internos
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ops.catalog_pipeline import load_catalog_csv, evaluate_catalog


DEFAULT_PATH = PROJECT_ROOT / "data" / "catalog" / "candidates_full.csv"


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _detect_keys(sample: Dict[str, Any]) -> Tuple[str | None, str | None]:
    id_key: str | None = None
    title_key: str | None = None

    for k in sample.keys():
        kl = str(k).strip().lower()

        if id_key is None:
            if kl.endswith("product_id") or kl in {"product_id", "id", "sku"}:
                id_key = k

        if title_key is None:
            if "title" in kl or "name" in kl:
                title_key = k

    return id_key, title_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=str,
        default=str(DEFAULT_PATH),
        help="Ruta al CSV de candidatos",
    )
    args = parser.parse_args()

    csv_path = Path(args.path)
    if not csv_path.is_absolute():
        csv_path = (PROJECT_ROOT / csv_path).resolve()

    if not csv_path.exists():
        _print_header("ERROR: CSV NO ENCONTRADO")
        print(f"Buscado en: {csv_path}")
        return

    _print_header("CANDIDATOS — CARGA DE CSV")
    print(f"Usando archivo:\n  {csv_path}")

    raw_catalog: List[Dict[str, Any]] = load_catalog_csv(csv_path)
    if not raw_catalog:
        _print_header("ERROR: CATALOGO VACIO")
        return

    sample_row = raw_catalog[0]
    id_key, title_key = _detect_keys(sample_row)

    _print_header("DEBUG KEYS DETECTADAS")
    print(f"Keys ejemplo: {list(sample_row.keys())}")
    print(f"id_key    : {repr(id_key)}")
    print(f"title_key : {repr(title_key)}")

    items, summary = evaluate_catalog(
        raw_catalog,
        total_test_budget=100.0,
    )

    paired: List[Tuple[Any, Dict[str, Any]]] = list(zip(items, raw_catalog))

    _print_header("RESUMEN")
    print(f"Total productos      : {summary.total_products}")
    print(f"Aprobados            : {summary.approved}")
    print(f"Rechazados           : {summary.rejected}")
    print(f"En revisión          : {summary.needs_review}")

    total_budget = sum(float(getattr(item, "allocated_test_budget", 0.0)) for item, _ in paired)
    print(f"Budget total asignado: {total_budget:.2f}")

    _print_header("RANKING POR SCORE (composite + quality)")
    sorted_pairs = sorted(
        paired,
        key=lambda pair: float(getattr(pair[0], "composite_score", 0.0)),
        reverse=True,
    )

    for item, raw in sorted_pairs:
        product_id = str(raw.get(id_key, "")).strip() if id_key else ""
        title = str(raw.get(title_key, "")).strip() if title_key else ""

        pid_str = product_id if product_id else "?"
        title_str = f" {title}" if title else ""

        comp = float(getattr(item, "composite_score", 0.0))
        qual = float(getattr(item, "quality_score", 0.0))
        budget = float(getattr(item, "allocated_test_budget", 0.0))
        capital_reason = str(getattr(item, "capital_reason", "")).strip()

        print(
            f"- {pid_str:>4}{title_str} | dec={item.final_decision:9} "
            f"| comp={comp:6.2f} | qual={qual:6.2f} "
            f"| budget={budget:6.2f} | reason={capital_reason}"
        )


if __name__ == "__main__":
    main()
