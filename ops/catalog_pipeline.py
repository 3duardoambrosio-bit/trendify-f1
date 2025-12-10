from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from infra.bitacora_auto import BitacoraAuto
from ops.capital_shield import CapitalShield
from synapse import product_evaluator


@dataclass
class CatalogItemResult:
    """
    Resultado consolidado de un producto en el pipeline F1.
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
    Resumen agregado del catálogo después de pasar por F1.
    """
    total_products: int
    approved: int
    rejected: int
    unknown: int
    total_test_budget: float
    avg_composite_score: Optional[float]
    avg_quality_score: Optional[float]


# ---------- Helpers de parsing CSV ----------


def _parse_bool(value: str) -> bool:
    v = str(value).strip().lower()
    return v in {"1", "true", "yes", "y", "t", "si", "sí"}


def _parse_field(key: str, value: str) -> Any:
    if value is None:
        return None

    raw = str(value).strip()
    if raw == "":
        return None

    # booleanos
    if key == "has_video":
        return _parse_bool(raw)

    # enteros típicos
    if key.endswith("_count") or key.endswith("_days"):
        try:
            return int(raw)
        except ValueError:
            # si no cuadra, se intenta como float/string
            pass

    # floats genéricos (price, cost, shipping_cost, supplier_rating, etc.)
    try:
        return float(raw)
    except ValueError:
        # fallback: string tal cual (product_id, nombres, etc.)
        return raw


def load_catalog_csv(path: Path) -> List[Dict[str, Any]]:
    """
    Carga un CSV de catálogo a una lista de dicts normalizados.
    """
    products: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            row: Dict[str, Any] = {
                key: _parse_field(key, value) for key, value in raw_row.items()
            }
            products.append(row)
    return products


# ---------- Pipeline principal ----------


def evaluate_catalog(
    products: Iterable[Dict[str, Any]],
    total_test_budget: float,
    bitacora: Optional[BitacoraAuto] = None,
) -> List[CatalogItemResult]:
    """
    Evalúa un conjunto de productos usando el stack actual (Buyer + Quality + Bitácora + CapitalShield).

    - Para cada producto llama a `evaluate_product` (que ya registra en Bitácora).
    - Usa `CapitalShield` para asignar un presupuesto de testeo por producto aprobado.
    """
    if bitacora is None:
        bitacora = BitacoraAuto()

    if total_test_budget <= 0:
        raise ValueError("total_test_budget debe ser > 0")

    # Ejemplo: si total_test_budget=300 => per_product_test_budget=30
    # El shield tiene su propio daily_cap interno (por defecto 30).
    per_product_test_budget = total_test_budget * 0.1

    # IMPORTANTE: usamos la firma original, sin kwargs raros.
    shield = CapitalShield()

    results: List[CatalogItemResult] = []

    for product in products:
        final_decision, record, quality = product_evaluator.evaluate_product(
            product,
            bitacora=bitacora,
        )

        product_id = record.get("product_id") or product.get("product_id") or "unknown"

        budget = 0.0
        capital_reason = "not_approved"

        if final_decision == "approved":
            decision = shield.register_spend(
                product_id=product_id,
                amount=per_product_test_budget,
            )
            if decision.allowed:
                budget = per_product_test_budget
                capital_reason = "ok"
            else:
                budget = 0.0
                capital_reason = decision.reason

        buyer_decision = record.get("buyer_decision")

        composite_score: Optional[float] = None
        buyer_scores = record.get("buyer_scores") or {}
        if "composite_score" in buyer_scores:
            try:
                composite_score = float(buyer_scores["composite_score"])
            except (TypeError, ValueError):
                composite_score = None

        quality_score: Optional[float] = None
        if hasattr(quality, "global_score"):
            try:
                quality_score = float(quality.global_score)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                quality_score = None

        results.append(
            CatalogItemResult(
                product_id=product_id,
                final_decision=final_decision,
                buyer_decision=buyer_decision,
                composite_score=composite_score,
                quality_score=quality_score,
                allocated_test_budget=float(budget),
                capital_reason=capital_reason,
            )
        )

    return results


def summarize_catalog(
    items: Iterable[CatalogItemResult],
) -> CatalogSummary:
    """
    Saca métricas agregadas del catálogo.
    """
    total = 0
    approved = 0
    rejected = 0
    unknown = 0
    total_budget = 0.0

    composite_values: List[float] = []
    quality_values: List[float] = []

    for item in items:
        total += 1
        total_budget += float(item.allocated_test_budget or 0.0)

        if item.final_decision == "approved":
            approved += 1
        elif item.final_decision == "rejected":
            rejected += 1
        else:
            unknown += 1

        if item.composite_score is not None:
            composite_values.append(float(item.composite_score))
        if item.quality_score is not None:
            quality_values.append(float(item.quality_score))

    avg_composite = (
        sum(composite_values) / len(composite_values) if composite_values else None
    )
    avg_quality = (
        sum(quality_values) / len(quality_values) if quality_values else None
    )

    return CatalogSummary(
        total_products=total,
        approved=approved,
        rejected=rejected,
        unknown=unknown,
        total_test_budget=total_budget,
        avg_composite_score=avg_composite,
        avg_quality_score=avg_quality,
    )
