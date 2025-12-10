from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from infra.bitacora_auto import BitacoraAuto


@dataclass
class QualityResult:
    """Resultado simple de calidad para mantener compatibilidad con el pipeline."""
    global_score: float


def _simple_scoring(product: Dict[str, Any]) -> Tuple[str, Dict[str, Any], QualityResult]:
    """
    Evaluador simplificado para el demo de catálogo.

    Usa solo campos básicos del catálogo:
    - price, cost, shipping_cost
    - supplier_rating
    - reviews_count

    No depende de BuyerBlock ni de QualityGate para evitar problemas de API.
    """

    price = float(product.get("price", 0.0) or 0.0)
    cost = float(product.get("cost", 0.0) or 0.0)
    shipping = float(product.get("shipping_cost", 0.0) or 0.0)
    rating = float(product.get("supplier_rating", 0.0) or 0.0)
    reviews = float(product.get("reviews_count", 0.0) or 0.0)

    # margen sobre precio (0–1)
    margin = 0.0
    if price > 0:
        margin = max(0.0, min(1.0, (price - cost - shipping) / price))

    # normalizaciones burdas solo para demo
    rating_norm = max(0.0, min(1.0, (rating - 3.0) / 2.0))      # 3★ → 0, 5★ → 1
    reviews_norm = max(0.0, min(1.0, reviews / 200.0))          # 0–200 → 0–1

    composite_score = 0.5 * margin + 0.3 * rating_norm + 0.2 * reviews_norm

    # reglas sencillas:
    # - margen >= 0.3
    # - rating >= 4.0
    # - reviews >= 50
    if margin >= 0.30 and rating >= 4.0 and reviews >= 50:
        buyer_decision = "approved"
    else:
        buyer_decision = "rejected"

    quality_score = composite_score  # para el demo, igualamos calidad al composite
    quality = QualityResult(global_score=quality_score)

    record: Dict[str, Any] = {
        "product_id": product.get("product_id"),
        "buyer_decision": buyer_decision,
        "buyer_scores": {
            "composite_score": composite_score,
            "margin": margin,
            "rating_norm": rating_norm,
            "reviews_norm": reviews_norm,
        },
        "quality_global_score": quality_score,
        "final_decision": buyer_decision,
    }

    return buyer_decision, record, quality


def evaluate_product(
    product: Dict[str, Any],
    bitacora: Optional[BitacoraAuto] = None,
) -> Tuple[str, Dict[str, Any], QualityResult]:
    """
    Punto único de entrada para evaluar un producto desde SYNAPSE.

    - Recibe un dict de producto (catálogo normalizado).
    - Devuelve:
        - final_decision: "approved" | "rejected" | "unknown"
        - record: dict con todos los datos internos
        - quality: objeto con atributo .global_score

    Esta versión está desacoplada de BuyerBlock/QualityGate para evitar
    errores de API en los demos, pero mantiene la misma interfaz.
    """

    if bitacora is None:
        bitacora = BitacoraAuto()

    final_decision, record, quality = _simple_scoring(product)

    # Logueamos en Bitácora en formato consistente con el resto del sistema
    composite_score = record.get("buyer_scores", {}).get("composite_score")

    bitacora.log(
        entry_type="product_evaluation",
        data={
            "product_id": record.get("product_id"),
            "final_decision": record.get("final_decision"),
            "buyer_decision": record.get("buyer_decision"),
            "quality_score": record.get("quality_global_score"),
            "composite_score": composite_score,
        },
    )

    return final_decision, record, quality
