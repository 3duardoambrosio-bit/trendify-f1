# ops/catalog_pipeline.py

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from infra.bitacora_auto import BitacoraAuto
from ops.capital_shield import CapitalShield
from synapse import product_evaluator

# Ruta por defecto para el catálogo demo
CATALOG_PATH: Path = Path("data/catalog/demo_catalog.csv")


@dataclass
class CatalogItemResult:
    """
    Resultado agregado por producto en el pipeline de catálogo.
    """
    product_id: str
    final_decision: str
    buyer_decision: Optional[str]
    composite_score: Optional[float]
    quality_score: Optional[float]
    allocated_test_budget: float
    capital_reason: str


@dataclass
class CatalogSummary:
    """
    Resumen agregado del catálogo.
    """
    total_products: int
    approved: int
    rejected: int
    unknown: int
    total_test_budget: float
    avg_composite_score: float
    avg_quality_score: float


# ------------------------
# Helpers internos
# ------------------------


_FLOAT_FIELDS = {
    "price",
    "cost",
    "shipping_cost",
    "supplier_rating",
}

_INT_FIELDS = {
    "reviews_count",
    "delivery_time_days",
    "images_count",
}

_BOOL_FIELDS = {
    "has_video",
}


def _parse_field(name: str, value: str) -> Any:
    """Castea campos conocidos a su tipo correcto."""
    if value is None:
        return None

    value = value.strip()
    if value == "":
        return None

    if name in _FLOAT_FIELDS:
        return float(value)

    if name in _INT_FIELDS:
        return int(value)

    if name in _BOOL_FIELDS:
        v = value.lower()
        return v in {"1", "true", "yes", "y", "t"}

    return value


# ------------------------
# API pública
# ------------------------


def load_catalog_csv(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Carga un catálogo desde CSV y regresa una lista de dicts tipados.

    Si `path` es None, usa CATALOG_PATH por defecto.
    El CSV se asume con encabezados en la primera fila.
    """
    if path is None:
        path = CATALOG_PATH

    if not path.exists():
        raise FileNotFoundError(f"Catálogo no encontrado en: {path}")

    rows: List[Dict[str, Any]] = []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            row: Dict[str, Any] = {
                key: _parse_field(key, value) for key, value in raw_row.items()
            }
            rows.append(row)

    return rows


def evaluate_catalog(
    products: Iterable[Dict[str, Any]],
    total_test_budget: float,
    bitacora: Optional[BitacoraAuto] = None,
) -> List[CatalogItemResult]:
    """
    Evalúa un conjunto de productos usando el stack actual
    (Buyer + Quality + Bitácora + CapitalShield).

    - Para cada producto llama a `product_evaluator.evaluate_product`
      (que ya registra en Bitácora).
    - Usa `CapitalShield` para asignar un presupuesto de testeo fijo
      por producto aprobado.
    """
    if bitacora is None:
        bitacora = BitacoraAuto()

    if total_test_budget <= 0:
        raise ValueError("total_test_budget debe ser > 0")

    # Presupuesto estándar por producto; el shield bloquea si se rebasa el cap global
    per_product_test_budget: float = total_test_budget * 0.1

    # Usa CapitalShield con los defaults que ya están testeados
    shield = CapitalShield()

    results: List[CatalogItemResult] = []

    for product in products:
        # evaluate_product ya escribe en Bitácora
        final_decision, record, quality = product_evaluator.evaluate_product(
            product, bitacora=bitacora
        )

        product_id: str = record.get("product_id") or product.get("product_id", "")

        buyer_decision: Optional[str] = record.get("buyer_decision")

        raw_composite = record.get("buyer_scores", {}).get("composite_score")
        composite_score: Optional[float] = (
            float(raw_composite) if raw_composite is not None else None
        )

        raw_quality = getattr(quality, "global_score", None)
        quality_score: Optional[float] = (
            float(raw_quality) if raw_quality is not None else None
        )

        allocated_test_budget: float = 0.0
        capital_reason: str = "not_approved"

        if final_decision == "approved":
            decision = shield.register_spend(product_id, per_product_test_budget)
            capital_reason = decision.reason
            if decision.allowed:
                allocated_test_budget = per_product_test_budget
            else:
                allocated_test_budget = 0.0
        else:
            capital_reason = "not_approved"

        results.append(
            CatalogItemResult(
                product_id=product_id,
                final_decision=final_decision,
                buyer_decision=buyer_decision,
                composite_score=composite_score,
                quality_score=quality_score,
                allocated_test_budget=allocated_test_budget,
                capital_reason=capital_reason,
            )
        )

    return results


def summarize_catalog(results: Iterable[CatalogItemResult]) -> CatalogSummary:
    """
    Resume los resultados del catálogo en métricas agregadas.
    """
    items: List[CatalogItemResult] = list(results)
    total: int = len(items)

    approved: int = sum(1 for r in items if r.final_decision == "approved")
    rejected: int = sum(1 for r in items if r.final_decision == "rejected")
    unknown: int = total - approved - rejected

    total_test_budget: float = sum(r.allocated_test_budget for r in items)

    composite_vals = [
        r.composite_score for r in items if r.composite_score is not None
    ]
    quality_vals = [r.quality_score for r in items if r.quality_score is not None]

    avg_composite_score: float = (
        sum(composite_vals) / len(composite_vals) if composite_vals else 0.0
    )
    avg_quality_score: float = (
        sum(quality_vals) / len(quality_vals) if quality_vals else 0.0
    )

    return CatalogSummary(
        total_products=total,
        approved=approved,
        rejected=rejected,
        unknown=unknown,
        total_test_budget=total_test_budget,
        avg_composite_score=avg_composite_score,
        avg_quality_score=avg_quality_score,
    )
