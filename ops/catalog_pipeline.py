from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from infra.bitacora_auto import BitacoraAuto
from ops.capital_shield_v2 import CapitalShieldV2
from synapse import product_evaluator


_MONEY_QUANT = Decimal("0.01")


# ---------------------------------------------------------------------------
# MODELOS DE RESULTADOS
# ---------------------------------------------------------------------------


@dataclass
class CatalogItemResult:
    """
    Resultado de un producto en el catálogo.

    Campos alineados con lo que usan los tests:
    - product_id
    - final_decision: "approved" | "rejected" | "needs_review" | "unknown"
    - buyer_decision: decisión del BuyerBlock (puede ser None)
    - composite_score: score compuesto del buyer (0-1 o 0-100, depende del stack)
    - quality_score: score de calidad (Quality-Gate)
    - allocated_test_budget: presupuesto de testeo asignado por CapitalShield
    - capital_reason: texto corto con la razón de la asignación
    """

    product_id: str
    final_decision: str
    buyer_decision: Optional[str] = None
    composite_score: Optional[float] = None
    quality_score: Optional[float] = None
    allocated_test_budget: Decimal = Decimal("0.00")
    capital_reason: str = ""


@dataclass
class CatalogSummary:
    """
    Resumen agregador del catálogo evaluado.

    Los tests esperan estos atributos:
    - total_products
    - approved
    - rejected
    - needs_review
    - unknown
    """

    total_products: int
    approved: int
    rejected: int
    needs_review: int
    unknown: int


# ---------------------------------------------------------------------------
# LOAD CATALOG CSV
# ---------------------------------------------------------------------------


def _money(value: Any, *, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite decimal")
    if value in (None, ""):
        raise ValueError(f"{field_name} must be a finite decimal")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a finite decimal") from None
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _parse_bool(value: str) -> bool:
    """Convierte strings tipo 'true'/'false' a bool."""
    v = str(value).strip().lower()
    if v in {"true", "1", "yes", "y", "si", "sí"}:
        return True
    if v in {"false", "0", "no", "n"}:
        return False
    return False


def load_catalog_csv(path: Path) -> List[Dict[str, Any]]:
    """
    Carga un CSV de catálogo y castea tipos básicos.

    Money fields are parsed as Decimal so catalog ingestion cannot become a
    parallel float-money authority.
    """
    products: List[Dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            product: Dict[str, Any] = dict(row)

            if "product_id" in product and product["product_id"] is not None:
                product["product_id"] = str(product["product_id"])

            for key in ("price", "cost", "shipping_cost", "landed_cost", "estimated_cac"):
                if key in product and product[key] not in ("", None):
                    product[key] = _money(product[key], field_name=key)

            if "supplier_rating" in product and product["supplier_rating"] not in ("", None):
                product["supplier_rating"] = float(product["supplier_rating"])

            for key in ("reviews_count", "delivery_time_days", "images_count"):
                if key in product and product[key] not in ("", None):
                    product[key] = int(product[key])

            if "has_video" in product and product["has_video"] not in ("", None):
                product["has_video"] = _parse_bool(product["has_video"])

            products.append(product)

    return products


# ---------------------------------------------------------------------------
# RESUMEN DEL CATÁLOGO
# ---------------------------------------------------------------------------


def summarize_catalog(items: List[CatalogItemResult]) -> CatalogSummary:
    """
    Calcula un resumen simple de decisiones del catálogo.
    """
    total = len(items)
    approved = 0
    rejected = 0
    needs_review = 0
    unknown = 0

    for item in items:
        decision = item.final_decision
        if decision == "approved":
            approved += 1
        elif decision == "rejected":
            rejected += 1
        elif decision == "needs_review":
            needs_review += 1
        else:
            unknown += 1

    return CatalogSummary(
        total_products=total,
        approved=approved,
        rejected=rejected,
        needs_review=needs_review,
        unknown=unknown,
    )


# ---------------------------------------------------------------------------
# CORE: EVALUACIÓN DE CATÁLOGO
# ---------------------------------------------------------------------------


def _evaluate_catalog_core(
    products: Iterable[Dict[str, Any]],
    total_test_budget: Decimal | float | str,
    capital_shield: Optional[CapitalShieldV2] = None,
    bitacora: Optional[BitacoraAuto] = None,
) -> List[CatalogItemResult]:
    """
    Core de evaluación de catálogo.

    - Llama a synapse.product_evaluator.evaluate_product(product).
    - product_evaluator delegates commercial money authority to the Decimal
      financial engine.
    - Asigna presupuesto SÓLO a los productos aprobados.
    """
    total_budget = _money(total_test_budget, field_name="total_test_budget")
    if total_budget <= Decimal("0.00"):
        raise ValueError("total_test_budget debe ser > 0")

    product_list = list(products)

    results: List[CatalogItemResult] = []

    for product in product_list:
        buyer_decision, record, quality = product_evaluator.evaluate_product(product)

        product_id = record.get("product_id") or product.get("product_id") or ""
        final_decision = record.get("final_decision") or buyer_decision or "unknown"
        buyer_scores = record.get("buyer_scores") or {}
        composite_score = buyer_scores.get("composite_score")

        quality_score: Optional[float] = None
        if "quality_score" in record:
            quality_score = record["quality_score"]
        else:
            quality_score = getattr(quality, "global_score", None)

        item = CatalogItemResult(
            product_id=product_id,
            final_decision=final_decision,
            buyer_decision=buyer_decision,
            composite_score=composite_score,
            quality_score=quality_score,
            allocated_test_budget=Decimal("0.00"),
            capital_reason="not_approved",
        )
        results.append(item)

    approved_items = [r for r in results if r.final_decision == "approved"]
    n_approved = len(approved_items)

    if n_approved > 0:
        per_product_budget = (total_budget / Decimal(n_approved)).quantize(
            _MONEY_QUANT,
            rounding=ROUND_HALF_UP,
        )

        for item in approved_items:
            if capital_shield is None:
                item.allocated_test_budget = per_product_budget
                item.capital_reason = "approved"
                continue

            decision = capital_shield.decide_for_product(
                final_decision=item.final_decision,
                requested_amount=per_product_budget,
            )
            item.allocated_test_budget = decision.allocated
            item.capital_reason = str(decision.reason)

    return results


# ---------------------------------------------------------------------------
# API PÚBLICA: evaluate_catalog
# ---------------------------------------------------------------------------


def evaluate_catalog(
    products: Optional[Iterable[Dict[str, Any]]] = None,
    total_test_budget: Decimal | float | str = Decimal("0.00"),
    bitacora: Optional[BitacoraAuto] = None,
    catalog_path: Optional[Path] = None,
    capital_shield: Optional[CapitalShieldV2] = None,
) -> Tuple[List[CatalogItemResult], CatalogSummary]:
    """
    Función pública de evaluación de catálogo.
    """
    if catalog_path is not None:
        products_list = load_catalog_csv(catalog_path)
    else:
        if products is None:
            raise ValueError("Debes pasar 'products' o 'catalog_path'")
        products_list = list(products)

    results = _evaluate_catalog_core(
        products=products_list,
        total_test_budget=total_test_budget,
        capital_shield=capital_shield,
        bitacora=bitacora,
    )

    summary = summarize_catalog(results)
    return results, summary