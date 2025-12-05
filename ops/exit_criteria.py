from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any


class CriteriaLevel(str, Enum):
    PRODUCT = "product"
    ACCOUNT = "account"  # futuro


class Verdict(str, Enum):
    CONTINUE = "continue"
    SCALE = "scale"
    PAUSE = "pause"
    KILL = "kill"


@dataclass
class ProductPerformanceSnapshot:
    """
    Snapshot simple de desempeño de un producto para tomar decisión de EXIT.

    NOTA F1:
    - Todo es a nivel agregado (producto completo, no campañas).
    - No dependemos aún de Shopify / Ads reales, solo de números que le pasemos.
    """

    product_id: str
    days_running: int
    total_spend: float
    total_revenue: float
    quality_score: float  # 0–1 (venir de QUALITY-GATE cuando exista el hook)

    # Campo flexible para futuro (conversiones, refunds, etc.)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def roas(self) -> float:
        if self.total_spend <= 0:
            return 0.0
        return self.total_revenue / self.total_spend

    @property
    def is_profitable(self) -> bool:
        # ROAS > 1 = ya no estás perdiendo dinero a nivel bruto
        return self.roas > 1.0


@dataclass
class ExitDecision:
    verdict: Verdict
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class ExitCriteriaEngine:
    """
    Motor determinista de CRITERIOS-EXIT v0.1 (solo producto).

    Reglas F1 (simple pero seria):
    1) Si no hay data suficiente → CONTINUE (insufficient_data)
    2) Si ROAS == 0 después de cierto gasto → KILL
    3) Si ROAS < min_roas_to_continue → KILL
    4) Si ROAS >= scale_roas_threshold y quality alta → SCALE
    5) En cualquier otro caso → CONTINUE (keep_testing)
    """

    def __init__(
        self,
        min_days_for_decision: int = 2,
        min_spend_for_decision: float = 10.0,
        zero_roas_hard_kill_spend: float = 30.0,
        min_roas_to_continue: float = 1.2,
        scale_roas_threshold: float = 2.0,
        scale_quality_threshold: float = 0.8,
    ) -> None:
        self.min_days_for_decision = min_days_for_decision
        self.min_spend_for_decision = min_spend_for_decision
        self.zero_roas_hard_kill_spend = zero_roas_hard_kill_spend
        self.min_roas_to_continue = min_roas_to_continue
        self.scale_roas_threshold = scale_roas_threshold
        self.scale_quality_threshold = scale_quality_threshold

    def evaluate_product(self, snapshot: ProductPerformanceSnapshot) -> ExitDecision:
        # 1) Data insuficiente → no tomes decisiones fuertes
        if (
            snapshot.days_running < self.min_days_for_decision
            or snapshot.total_spend < self.min_spend_for_decision
        ):
            return ExitDecision(
                verdict=Verdict.CONTINUE,
                reason="insufficient_data",
                details=self._base_details(snapshot),
            )

        # 2) ROAS == 0 con gasto ya serio → KILL
        if snapshot.total_revenue <= 0 and snapshot.total_spend >= self.zero_roas_hard_kill_spend:
            return ExitDecision(
                verdict=Verdict.KILL,
                reason="zero_roas_after_threshold",
                details=self._base_details(snapshot),
            )

        # 3) ROAS por debajo del mínimo aceptable → KILL
        if snapshot.roas < self.min_roas_to_continue:
            return ExitDecision(
                verdict=Verdict.KILL,
                reason="roas_below_minimum",
                details=self._base_details(snapshot),
            )

        # 4) Ganador claro → SCALE
        if snapshot.roas >= self.scale_roas_threshold and snapshot.quality_score >= self.scale_quality_threshold:
            return ExitDecision(
                verdict=Verdict.SCALE,
                reason="scale_winner",
                details=self._base_details(snapshot),
            )

        # 5) En medio de la curva → seguir probando
        return ExitDecision(
            verdict=Verdict.CONTINUE,
            reason="keep_testing",
            details=self._base_details(snapshot),
        )

    @staticmethod
    def _base_details(snapshot: ProductPerformanceSnapshot) -> Dict[str, Any]:
        return {
            "product_id": snapshot.product_id,
            "days_running": snapshot.days_running,
            "total_spend": snapshot.total_spend,
            "total_revenue": snapshot.total_revenue,
            "roas": snapshot.roas,
            "quality_score": snapshot.quality_score,
        }


# Helper de módulo para no andar creando engine a mano en todos lados
_default_engine = ExitCriteriaEngine()


def evaluate_product_exit(snapshot: ProductPerformanceSnapshot) -> ExitDecision:
    """
    Atajo simple:
        decision = evaluate_product_exit(snapshot)
    """
    return _default_engine.evaluate_product(snapshot)
