# synapse/quality_gate.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from buyer.schemas import ProductSchema
from infra.logging_config import get_logger

logger = get_logger(__name__)


# =========================
# ENUMS / TIPOS BÁSICOS
# =========================


class QualityArea(str, Enum):
    PRODUCT = "product"


class CheckType(str, Enum):
    ANTI_GENERIC = "anti_generic"
    INTENTION = "intention"
    DETAIL_SCAN = "detail_scan"


class EnforcementLevel(str, Enum):
    GUIDE = "guide"   # Solo guía mental
    SOFT = "soft"     # Warning, tú decides
    HARD = "hard"     # Bloquea


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


# =========================
# MODELOS DE QUALITY
# =========================


@dataclass
class QualityCheck:
    check_id: str                      # p.ej. "product.anti_generic.negative_margin"
    check_type: CheckType
    area: QualityArea
    description: str
    enforcement_level: EnforcementLevel
    status: CheckStatus = CheckStatus.PASSED
    failed_reason: Optional[str] = None
    score_contribution: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityCheckResult:
    check: QualityCheck
    passed: bool
    score: Optional[float] = None  # 0-1 si aplica
    details: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QualityGateResult:
    area: QualityArea
    subject_type: str                  # "product"
    subject_id: Optional[str] = None   # product_id

    global_passed: bool = False
    global_score: float = 0.0          # 0-1
    lock_level: EnforcementLevel = EnforcementLevel.GUIDE

    checks: List[QualityCheckResult] = field(default_factory=list)

    anti_generic_passed: bool = False
    intention_passed: bool = True      # en Fase 1 no aplicamos intention-check real
    detail_score: float = 0.0

    hard_failures: List[str] = field(default_factory=list)
    soft_warnings: List[str] = field(default_factory=list)

    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    evaluated_by: str = "system"

    def can_proceed(self) -> bool:
        if self.lock_level == EnforcementLevel.HARD:
            return len(self.hard_failures) == 0
        return True

    def needs_attention(self) -> bool:
        return len(self.soft_warnings) > 0


# =========================
# QUALITY-GATE: PRODUCTO
# =========================


def _calculate_margin(product: ProductSchema) -> float:
    if product.sale_price is None or product.sale_price <= 0:
        return 0.0
    return float(product.sale_price - product.cost_price) / float(product.sale_price)


def _is_generic_name(name: str) -> bool:
    """
    Heurística simple para nombres genéricos tipo "New 2024 Item".
    No es perfecto, pero para Fase 1 basta.
    """
    n = name.strip().lower()
    generic_tokens = ["item", "product", "new", "2024", "2025"]
    # Muy corto y con palabras genéricas → sospechoso
    if len(n) < 10 and any(t in n for t in generic_tokens):
        return True
    # Nombre súper genérico
    if n in {"item", "product", "new product", "new item"}:
        return True
    return False


def quality_check_product(product: ProductSchema) -> QualityGateResult:
    """
    QUALITY-GATE mínimo para PRODUCTO en Fase 1.

    Hard locks:
    - Margen negativo → bloqueado
    - Nombre genérico sospechoso → bloqueado

    Soft warnings:
    - Margen < 30%
    - Trust score < 6 (si existe)
    """
    checks: List[QualityCheckResult] = []
    hard_failures: List[str] = []
    soft_warnings: List[str] = []

    margin = _calculate_margin(product)
    trust_score = float(product.trust_score) if product.trust_score is not None else 0.0

    # ---------------------------
    # HARD CHECK: margen negativo
    # ---------------------------
    c1 = QualityCheck(
        check_id="product.anti_generic.negative_margin",
        check_type=CheckType.ANTI_GENERIC,
        area=QualityArea.PRODUCT,
        description="Rechaza productos con margen negativo",
        enforcement_level=EnforcementLevel.HARD,
    )
    if margin < 0:
        c1.status = CheckStatus.FAILED
        c1.failed_reason = "margin_negative"
        hard_failures.append("margin_negative")
        checks.append(
            QualityCheckResult(
                check=c1,
                passed=False,
                score=0.0,
                details="Producto con margen negativo",
            )
        )
    else:
        checks.append(
            QualityCheckResult(
                check=c1,
                passed=True,
                score=1.0,
                details="Margen no es negativo",
            )
        )

    # ---------------------------
    # HARD CHECK: nombre genérico
    # ---------------------------
    c2 = QualityCheck(
        check_id="product.anti_generic.generic_name",
        check_type=CheckType.ANTI_GENERIC,
        area=QualityArea.PRODUCT,
        description="Detecta nombres genéricos tipo 'New 2024 Item'",
        enforcement_level=EnforcementLevel.HARD,
    )
    if _is_generic_name(product.name):
        c2.status = CheckStatus.FAILED
        c2.failed_reason = "generic_name"
        hard_failures.append("generic_name")
        checks.append(
            QualityCheckResult(
                check=c2,
                passed=False,
                score=0.0,
                details="Nombre de producto demasiado genérico",
            )
        )
    else:
        checks.append(
            QualityCheckResult(
                check=c2,
                passed=True,
                score=1.0,
                details="Nombre de producto OK",
            )
        )

    # ---------------------------
    # SOFT WARNING: margen bajo
    # ---------------------------
    c3 = QualityCheck(
        check_id="product.detail.low_margin",
        check_type=CheckType.DETAIL_SCAN,
        area=QualityArea.PRODUCT,
        description="Warning si margen < 30%",
        enforcement_level=EnforcementLevel.SOFT,
    )
    if margin < 0.30:
        c3.status = CheckStatus.WARNING
        soft_warnings.append("low_margin")
        checks.append(
            QualityCheckResult(
                check=c3,
                passed=True,
                score=margin,
                details=f"Margen bajo: {margin:.2f}",
            )
        )
    else:
        checks.append(
            QualityCheckResult(
                check=c3,
                passed=True,
                score=margin,
                details=f"Margen saludable: {margin:.2f}",
            )
        )

    # ---------------------------
    # SOFT WARNING: trust bajo
    # ---------------------------
    c4 = QualityCheck(
        check_id="product.detail.low_trust",
        check_type=CheckType.DETAIL_SCAN,
        area=QualityArea.PRODUCT,
        description="Warning si trust_score < 6",
        enforcement_level=EnforcementLevel.SOFT,
    )
    if trust_score < 6.0:
        c4.status = CheckStatus.WARNING
        soft_warnings.append("low_trust_score")
        checks.append(
            QualityCheckResult(
                check=c4,
                passed=True,
                score=trust_score / 10.0,
                details=f"Trust bajo: {trust_score:.1f}",
            )
        )
    else:
        checks.append(
            QualityCheckResult(
                check=c4,
                passed=True,
                score=trust_score / 10.0,
                details=f"Trust saludable: {trust_score:.1f}",
            )
        )

    # ---------------------------
    # Agregación de score / lock
    # ---------------------------
    if hard_failures:
        global_score = 0.0
        lock_level = EnforcementLevel.HARD
        global_passed = False
        anti_generic_passed = False
    else:
        # Base 1.0, cada warning baja 0.2 (mínimo 0.0)
        global_score = max(0.0, 1.0 - 0.2 * len(soft_warnings))
        lock_level = EnforcementLevel.SOFT if soft_warnings else EnforcementLevel.GUIDE
        global_passed = True
        anti_generic_passed = True

    detail_score = global_score  # en Fase 1 usamos el mismo

    result = QualityGateResult(
        area=QualityArea.PRODUCT,
        subject_type="product",
        subject_id=product.product_id,
        global_passed=global_passed,
        global_score=global_score,
        lock_level=lock_level,
        checks=checks,
        anti_generic_passed=anti_generic_passed,
        intention_passed=True,
        detail_score=detail_score,
        hard_failures=hard_failures,
        soft_warnings=soft_warnings,
    )

    logger.info(
        "Quality-Gate product evaluation",
        extra={
            "extra_data": {
                "product_id": product.product_id,
                "global_passed": result.global_passed,
                "global_score": result.global_score,
                "lock_level": result.lock_level.value,
                "hard_failures": result.hard_failures,
                "soft_warnings": result.soft_warnings,
            }
        },
    )

    return result
