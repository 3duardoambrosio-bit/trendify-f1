from __future__ import annotations

"""
COD Risk Scorer — cod_risk_scoring.

Modelo determinístico simple para decidir si ofrecer contra-entrega (COD).
Score ∈ [0, 1].

Factores:
- amount / max_cod_amount (cap 1.0)
- rural boost
- previous_rejections boost (cap 0.45)

__MARKER__ embedded in module constant below.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

import deal

__MARKER__ = "SESSION_S11_cod_risk_scorer_2026-03-02"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodRiskConfig:
    max_cod_amount_mxn: Decimal = Decimal("2000")
    high_risk_threshold: Decimal = Decimal("0.70")
    medium_risk_threshold: Decimal = Decimal("0.40")
    rural_risk_boost: Decimal = Decimal("0.20")


@dataclass(frozen=True)
class CodRiskResult:
    score: Decimal  # 0..1
    risk_level: str  # low/medium/high
    cod_allowed: bool
    reason: str


class CodRiskScorer:
    def __init__(self, config: CodRiskConfig | None = None) -> None:
        self._cfg = config or CodRiskConfig()

    @deal.pre(lambda self, amount_mxn, postal_code, is_rural, previous_rejections:
              isinstance(amount_mxn, Decimal) and amount_mxn >= Decimal("0"))
    @deal.pre(lambda self, amount_mxn, postal_code, is_rural, previous_rejections:
              isinstance(previous_rejections, int) and previous_rejections >= 0)
    @deal.post(lambda result: Decimal("0") <= result.score <= Decimal("1"))
    @deal.post(lambda result: result.risk_level in ("low", "medium", "high"))
    def score_order(
        self,
        amount_mxn: Decimal,
        postal_code: str,
        is_rural: bool = False,
        previous_rejections: int = 0,
    ) -> CodRiskResult:
        if amount_mxn > self._cfg.max_cod_amount_mxn:
            return CodRiskResult(
                score=Decimal("1"),
                risk_level="high",
                cod_allowed=False,
                reason="amount_exceeds_max_cod_2000",
            )

        denom = self._cfg.max_cod_amount_mxn
        if denom <= Decimal("0"):
            # Guardrail: config inválida -> fail closed
            return CodRiskResult(
                score=Decimal("1"),
                risk_level="high",
                cod_allowed=False,
                reason="invalid_config_max_cod_amount",
            )

        score = (amount_mxn / denom)
        if score > Decimal("1"):
            score = Decimal("1")

        if is_rural:
            score += self._cfg.rural_risk_boost

        if previous_rejections > 0:
            score += min(Decimal(previous_rejections) * Decimal("0.15"), Decimal("0.45"))

        if score > Decimal("1"):
            score = Decimal("1")
        if score < Decimal("0"):
            score = Decimal("0")

        if score > self._cfg.high_risk_threshold:
            return CodRiskResult(score=score, risk_level="high", cod_allowed=False, reason="high_risk")
        if score > self._cfg.medium_risk_threshold:
            return CodRiskResult(score=score, risk_level="medium", cod_allowed=True, reason="medium_risk_warning")
        return CodRiskResult(score=score, risk_level="low", cod_allowed=True, reason="ok")
