from typing import Dict, Any
from infra.logging_config import get_logger

logger = get_logger(__name__)


class DecisionLoggerAdapter:
    def log_decision(self, decision_data: Dict[str, Any]) -> None:
        """Log buyer decision in structured format"""
        logger.info(
            "Buyer decision made",
            extra={
                "extra_data": {
                    "decision_id": decision_data.get("decision_id"),
                    "product_id": decision_data.get("product_id"),
                    "decision": decision_data.get("decision"),
                    "reasons": decision_data.get("reasons", []),
                    "scores": decision_data.get("scores", {}),
                    "model_used": decision_data.get("model_used"),
                    "processing_time_ms": decision_data.get("metadata", {}).get(
                        "processing_time_ms", 0
                    ),
                    "operation": "buyer_decision",
                }
            },
        )
