from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import log1p
from typing import Any, Dict, Mapping, Optional, Tuple

from core.scoring import BayesianScore
from infra.bitacora_auto import BitacoraAuto
from synapse.financial.adapters import candidate_to_financial_input
from synapse.financial.evaluation import Decision, FinancialResult, ScenarioName, evaluate_financials


@dataclass
class QualityResult:
    global_score: float


_MONEY_ZERO = Decimal("0.00")


def _confidence_from_reviews(reviews: int) -> float:
    r = max(int(reviews), 0)
    denom = log1p(2000)
    if denom <= 0:
        return 0.0
    return min(1.0, log1p(r) / denom)


def _to_decimal(value: Any, *, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a decimal")
    if value in (None, ""):
        raise ValueError(f"{field_name} must be a decimal")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a decimal") from None
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _optional_decimal(value: Any, *, default: Decimal = _MONEY_ZERO) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return _to_decimal(value, field_name="optional_decimal")
    except ValueError:
        return default


def _candidate_for_financial_engine(product: Mapping[str, Any]) -> Dict[str, Any]:
    candidate: Dict[str, Any] = dict(product)

    product_id = candidate.get("product_id") or candidate.get("id") or ""
    name = candidate.get("name") or candidate.get("title") or product_id or "unknown_product"
    candidate["product_id"] = str(product_id)
    candidate["name"] = str(name)

    if "landed_cost" not in candidate:
        cost = _optional_decimal(candidate.get("cost"))
        shipping_cost = _optional_decimal(candidate.get("shipping_cost"))
        candidate["landed_cost"] = cost + shipping_cost

    return candidate


def _decision_to_catalog_decision(decision: Decision) -> str:
    if decision == Decision.PASS:
        return "approved"
    if decision == Decision.WATCH:
        return "needs_review"
    return "rejected"


def _score_from_financial_result(
    result: FinancialResult,
    *,
    rating: float,
    reviews: int,
) -> BayesianScore:
    base = result.scenarios[ScenarioName.BASE]
    margin_component = max(0.0, min(1.0, float(base.gross_margin_pct))) * 40.0
    rating_component = max(0.0, min(1.0, rating / 5.0)) * 30.0
    review_component = max(0.0, min(1.0, min(max(reviews, 0), 500) / 500.0)) * 30.0
    decision_floor = {
        Decision.PASS: 70.0,
        Decision.WATCH: 45.0,
        Decision.FAIL: 0.0,
        Decision.KILL: 0.0,
    }[result.decision]
    mean = max(decision_floor, margin_component + rating_component + review_component)
    return BayesianScore(
        mean=float(mean),
        confidence=float(_confidence_from_reviews(reviews)),
        sample_size=int(max(reviews, 0)),
    )


def _financial_record(
    *,
    product: Mapping[str, Any],
    result: FinancialResult,
    bayes: BayesianScore,
    quality_score: float,
) -> Tuple[str, Dict[str, Any], QualityResult]:
    final_decision = _decision_to_catalog_decision(result.decision)
    base = result.scenarios[ScenarioName.BASE]
    quality = QualityResult(global_score=quality_score)

    record: Dict[str, Any] = {
        "product_id": result.product_id,
        "buyer_decision": final_decision,
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
        "financial_decision": result.decision.value,
        "financial_reason_codes": list(result.reason_codes),
        "financial_risk_flags": list(result.risk_flags),
        "financial_base": {
            "price": str(base.price),
            "landed_cost": str(base.landed_cost),
            "estimated_cac": str(base.estimated_cac),
            "gross_margin_pct": str(base.gross_margin_pct),
            "contribution_margin": str(base.contribution_margin),
            "break_even_cac": str(base.break_even_cac),
            "estimated_profit": str(base.estimated_profit),
        },
    }

    return final_decision, record, quality


def _reject_invalid_financial_input(product: Mapping[str, Any], error: ValueError) -> Tuple[str, Dict[str, Any], QualityResult]:
    product_id = str(product.get("product_id") or product.get("id") or "")
    bayes = BayesianScore(mean=0.0, confidence=0.0, sample_size=0)
    quality = QualityResult(global_score=0.0)
    record: Dict[str, Any] = {
        "product_id": product_id,
        "buyer_decision": "rejected",
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
        "quality_score": 0.0,
        "final_decision": "rejected",
        "financial_decision": Decision.FAIL.value,
        "financial_reason_codes": ["INVALID_FINANCIAL_INPUT"],
        "financial_risk_flags": ["INVALID_FINANCIAL_INPUT"],
        "financial_error": str(error),
    }
    return "rejected", record, quality


def _simple_scoring(product: Dict[str, Any]) -> Tuple[str, Dict[str, Any], QualityResult]:
    """Compatibility wrapper; financial authority is the Decimal engine."""
    return _evaluate_with_financial_engine(product)


def _evaluate_with_financial_engine(product: Dict[str, Any]) -> Tuple[str, Dict[str, Any], QualityResult]:
    rating = float(product.get("rating", product.get("supplier_rating", 0.0)) or 0.0)
    reviews = int(product.get("reviews", product.get("reviews_count", 0)) or 0)

    try:
        financial_input = candidate_to_financial_input(_candidate_for_financial_engine(product))
        financial_result = evaluate_financials(financial_input)
    except ValueError as exc:
        return _reject_invalid_financial_input(product, exc)

    bayes = _score_from_financial_result(financial_result, rating=rating, reviews=reviews)
    quality_score = bayes.mean
    return _financial_record(
        product=product,
        result=financial_result,
        bayes=bayes,
        quality_score=quality_score,
    )


def evaluate_product(
    product: Dict[str, Any],
    bitacora: Optional[BitacoraAuto] = None,
) -> Tuple[str, Dict[str, Any], QualityResult]:
    if bitacora is None:
        bitacora = BitacoraAuto()

    buyer_decision, record, quality = _evaluate_with_financial_engine(product)

    composite_score = record.get("buyer_scores", {}).get("composite_score")
    bayes = record.get("buyer_scores", {}).get("bayesian", {})

    bitacora.log(
        entry_type="product_evaluation",
        data={
            "product_id": record.get("product_id"),
            "final_decision": record.get("final_decision"),
            "buyer_decision": record.get("buyer_decision"),
            "financial_decision": record.get("financial_decision"),
            "financial_reason_codes": record.get("financial_reason_codes"),
            "quality_score": record.get("quality_score"),
            "composite_score": composite_score,
            "confidence": bayes.get("confidence"),
            "range_low": bayes.get("range_low"),
            "range_high": bayes.get("range_high"),
        },
    )

    return buyer_decision, record, quality