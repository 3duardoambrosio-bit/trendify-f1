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

    Usa una regla muy básica basada en margen, rating y número de reseñas.
    Devuelve:
      - buyer_decision: "approved" o "rejected"
      - record: payload listo para bitácora / pipeline
      - quality: QualityResult con quality_score
    """
    price = float(product.get("price", 0.0) or 0.0)
    cost = float(product.get("cost", 0.0) or 0.0)
    shipping_cost = float(product.get("shipping_cost", 0.0) or 0.0)

    rating = float(
        product.get("rating", product.get("supplier_rating", 0.0)) or 0.0
    )
    reviews = int(
        product.get("reviews", product.get("reviews_count", 0)) or 0
    )

    # margen simplificado
    if price <= 0:
        margin = 0.0
    else:
        margin = (price - cost - shipping_cost) / price

    # composite_score ultra simple para el demo (0-100)
    composite_score = 0.0
    composite_score += max(0.0, min(1.0, margin)) * 0.4
    composite_score += max(0.0, min(1.0, rating / 5.0)) * 0.3
    composite_score += max(0.0, min(1.0, min(reviews, 500) / 500.0)) * 0.3
    composite_score *= 100.0

    if margin >= 0.30 and rating >= 4.0 and reviews >= 50:
        buyer_decision = "approved"
    else:
        buyer_decision = "rejected"

    # Para F1, calidad = composite (simplificado)
    quality_score = composite_score
    quality = QualityResult(global_score=quality_score)

    # 🔧 variables que te marcaba VSCode como “not defined”
    product_id = str(product.get("product_id") or product.get("id") or "")
    buyer_scores: Dict[str, float] = {"composite_score": composite_score}
    final_decision = buyer_decision

    record: Dict[str, Any] = {
        "product_id": product_id,
        "buyer_decision": buyer_decision,
        "buyer_scores": buyer_scores,
        "quality_score": quality_score,  # 👈 ya normalizado (antes era quality_global_score)
        "final_decision": final_decision,
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
