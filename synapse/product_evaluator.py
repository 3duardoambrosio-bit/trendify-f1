from __future__ import annotations

from dataclasses import dataclass
from math import log1p
from typing import Any, Dict, Optional, Tuple

from core.scoring import BayesianScore
from infra.bitacora_auto import BitacoraAuto


@dataclass
class QualityResult:
    global_score: float


def _confidence_from_reviews(reviews: int) -> float:
    r = max(int(reviews), 0)
    denom = log1p(2000)
    if denom <= 0:
        return 0.0
    return min(1.0, log1p(r) / denom)


def _simple_scoring(product: Dict[str, Any]) -> Tuple[str, Dict[str, Any], QualityResult]:
    price = float(product.get("price", 0.0) or 0.0)
    cost = float(product.get("cost", 0.0) or 0.0)
    shipping_cost = float(product.get("shipping_cost", 0.0) or 0.0)

    rating = float(product.get("rating", product.get("supplier_rating", 0.0)) or 0.0)
    reviews = int(product.get("reviews", product.get("reviews_count", 0)) or 0)

    if price <= 0:
        margin = 0.0
    else:
        margin = (price - cost - shipping_cost) / price

    composite = 0.0
    composite += max(0.0, min(1.0, margin)) * 0.4
    composite += max(0.0, min(1.0, rating / 5.0)) * 0.3
    composite += max(0.0, min(1.0, min(reviews, 500) / 500.0)) * 0.3
    composite *= 100.0

    buyer_decision = "approved" if (margin >= 0.30 and rating >= 4.0 and reviews >= 50) else "rejected"

    bayes = BayesianScore(
        mean=float(composite),
        confidence=float(_confidence_from_reviews(reviews)),
        sample_size=int(reviews),
    )

    quality_score = bayes.mean
    quality = QualityResult(global_score=quality_score)

    product_id = str(product.get("product_id") or product.get("id") or "")
    final_decision = buyer_decision

    record: Dict[str, Any] = {
        "product_id": product_id,
        "buyer_decision": buyer_decision,
        "buyer_scores": {
            "composite_score": bayes.mean,
            "bayesian": {
                "mean": bayes.mean,
                "confidence": bayes.confidence,
                "sample_size": bayes.sample_size,
                "range_low": bayes.range_low,
                "range_high": bayes.range_high,
            },
        },
        "quality_score": quality_score,
        "final_decision": final_decision,
    }

    return buyer_decision, record, quality


def evaluate_product(
    product: Dict[str, Any],
    bitacora: Optional[BitacoraAuto] = None,
) -> Tuple[str, Dict[str, Any], QualityResult]:
    if bitacora is None:
        bitacora = BitacoraAuto()

    buyer_decision, record, quality = _simple_scoring(product)

    composite_score = record.get("buyer_scores", {}).get("composite_score")
    bayes = record.get("buyer_scores", {}).get("bayesian", {})

    bitacora.log(
        entry_type="product_evaluation",
        data={
            "product_id": record.get("product_id"),
            "final_decision": record.get("final_decision"),
            "buyer_decision": record.get("buyer_decision"),
            "quality_score": record.get("quality_score"),
            "composite_score": composite_score,
            "confidence": bayes.get("confidence"),
            "range_low": bayes.get("range_low"),
            "range_high": bayes.get("range_high"),
        },
    )

    return buyer_decision, record, quality