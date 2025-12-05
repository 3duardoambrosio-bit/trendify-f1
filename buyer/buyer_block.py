import uuid
from datetime import datetime
from typing import List, Dict, Any, Tuple

from buyer.schemas import ProductSchema, BuyerDecisionSchema, Decision
from buyer.scoring_rules import ScoringRules
from infra.metrics_collector import metrics_collector
from infra.logging_config import get_logger

logger = get_logger(__name__)


class BuyerBlock:
    def __init__(self) -> None:
        self.scoring_rules = ScoringRules()
        self.metrics = metrics_collector

    def evaluate_batch(self, products: List[ProductSchema]) -> List[BuyerDecisionSchema]:
        """Evaluate a batch of products"""
        logger.info(
            "Starting batch evaluation",
            extra={
                "extra_data": {
                    "batch_size": len(products),
                    "operation": "evaluate_batch",
                }
            },
        )

        decisions: List[BuyerDecisionSchema] = []
        approved_count = 0
        rejected_count = 0
        needs_review_count = 0

        for product in products:
            try:
                decision = self.evaluate_product(product)
                decisions.append(decision)

                if decision.decision == Decision.APPROVED:
                    approved_count += 1
                elif decision.decision == Decision.REJECTED:
                    rejected_count += 1
                else:
                    needs_review_count += 1

            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Error evaluating product",
                    extra={
                        "extra_data": {
                            "product_id": product.product_id,
                            "error": str(e),
                            "operation": "evaluate_product",
                        }
                    },
                )
                decisions.append(self._create_error_decision(product, str(e)))
                rejected_count += 1

        self.metrics.increment_counter(
            "buyer_products_processed_total", value=len(products)
        )
        self.metrics.increment_counter(
            "buyer_decisions_total", {"decision": "approved"}, approved_count
        )
        self.metrics.increment_counter(
            "buyer_decisions_total", {"decision": "rejected"}, rejected_count
        )
        self.metrics.increment_counter(
            "buyer_decisions_total", {"decision": "needs_review"}, needs_review_count
        )

        logger.info(
            "Batch evaluation completed",
            extra={
                "extra_data": {
                    "total_processed": len(products),
                    "approved": approved_count,
                    "rejected": rejected_count,
                    "needs_review": needs_review_count,
                    "operation": "evaluate_batch",
                }
            },
        )

        return decisions

    def evaluate_product(self, product: ProductSchema) -> BuyerDecisionSchema:
        """Evaluate a single product"""
        start_time = datetime.now()

        evaluation = self.scoring_rules.evaluate_product(product)
        decision, reasons = self._make_decision(evaluation)

        processing_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        return BuyerDecisionSchema(
            decision_id=str(uuid.uuid4()),
            product_id=product.product_id,
            decision=decision,
            reasons=reasons,
            scores={
                "margin_score": evaluation["margin"],
                "trust_score": evaluation["trust_score"],
                "composite_score": evaluation["composite_score"],
            },
            model_used="deterministic_rules",
            evaluated_at=datetime.now().isoformat(),
            metadata={
                "processing_time_ms": processing_time_ms,
                "suspicion_flags": evaluation["suspicion_flags"],
            },
        )

    def _make_decision(self, evaluation: Dict[str, Any]) -> Tuple[Decision, List[str]]:
        flags: List[str] = evaluation["suspicion_flags"]
        margin_score: float = evaluation["margin"]
        trust_score: float = evaluation["trust_score"]
        composite_score: float = evaluation["composite_score"]

        # 1) Kill switch duro: margen muy bajo
        if "margin_below_threshold" in flags or margin_score < 0.2:
            return Decision.REJECTED, ["margin_below_threshold"]

        # 2) Caso ideal: nada raro y score alto → aprobado
        if not flags and composite_score >= 0.7:
            return Decision.APPROVED, ["product_meets_all_criteria"]

        # 3) Flags presentes pero no mortales → revisión manual
        if flags:
            return Decision.NEEDS_REVIEW, flags

        # 4) Default conservador
        return Decision.NEEDS_REVIEW, ["manual_review_required"]

    def _create_error_decision(
        self, product: ProductSchema, error: str
    ) -> BuyerDecisionSchema:
        return BuyerDecisionSchema(
            decision_id=str(uuid.uuid4()),
            product_id=product.product_id,
            decision=Decision.REJECTED,
            reasons=[f"evaluation_error: {error}"],
            scores={},
            model_used="error_fallback",
            evaluated_at=datetime.now().isoformat(),
            metadata={"error": error},
        )
