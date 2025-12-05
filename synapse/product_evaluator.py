# synapse/product_evaluator.py

from __future__ import annotations

from typing import Dict, Any, Tuple

from buyer.buyer_block import BuyerBlock
from buyer.schemas import ProductSchema
from infra.bitacora_auto import bitacora, EntryType
from synapse.quality_gate import quality_check_product, QualityGateResult


def evaluate_product_with_quality(
    product: ProductSchema,
) -> Tuple[Dict[str, Any], QualityGateResult]:
    """
    Orquesta el flujo:
    1) BuyerBlock evalúa (scores + decisión)
    2) QUALITY-GATE valida calidad mínima
    3) Bitácora registra TODO
    4) Regresa decisión final + resultado de quality
    """
    buyer = BuyerBlock()
    buyer_decision = buyer.evaluate_product(product)
    quality_result = quality_check_product(product)

    # Decisión final: si quality gate no pasa con hard lock → rechazado
    final_decision = buyer_decision.decision.value
    final_reasons = list(buyer_decision.reasons)

    if not quality_result.global_passed and quality_result.lock_level.value == "hard":
        final_decision = "rejected"
        final_reasons = list(final_reasons) + ["quality_gate_failed"]

    record = {
        "product_id": product.product_id,
        "buyer_decision": buyer_decision.decision.value,
        "buyer_reasons": buyer_decision.reasons,
        "buyer_scores": buyer_decision.scores,
        "quality_global_passed": quality_result.global_passed,
        "quality_global_score": quality_result.global_score,
        "quality_lock_level": quality_result.lock_level.value,
        "quality_hard_failures": quality_result.hard_failures,
        "quality_soft_warnings": quality_result.soft_warnings,
        "final_decision": final_decision,
        "final_reasons": final_reasons,
    }

    bitacora.log(
        entry_type=EntryType.PRODUCT_EVALUATION,
        data=record,
    )

    return record, quality_result
