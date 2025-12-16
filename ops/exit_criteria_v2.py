from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


KillAction = Literal["continue", "pause", "kill"]


@dataclass(frozen=True)
class KillDecision:
    """
    Decisión de vida/muerte para un experimento, producto o campaña.

    - action:
        - "continue" → sigue corriendo normal
        - "pause"    → frenar y revisar (no matar aún)
        - "kill"     → cortar presupuesto, se considera fracaso
    - reason: string legible para bitácora / dashboard
    """

    action: KillAction
    reason: str


# Umbrales fundacionales (se pueden parametrizar después vía config)
MIN_SPEND_FOR_DECISION = Decimal("10")   # antes de eso, no hay data seria
HARD_KILL_ROAS = 0.7                     # por debajo de esto: kill
SOFT_KILL_ROAS = 1.0                     # entre hard y soft: pause


def _clamp_roas(roas: float) -> float:
    """
    Acotamos ROAS a un rango razonable para evitar locuras numéricas.
    """
    if roas < 0.0:
        return 0.0
    if roas > 100.0:
        return 100.0
    return roas


def evaluate_kill_criteria(
    roas: float,
    spend: Decimal,
) -> KillDecision:
    """
    Árbol de decisión determinista para saber si matamos o no algo.

    Reglas versión 2 (fundacionales):

    1) Data insuficiente
       - Si spend < MIN_SPEND_FOR_DECISION → "continue"
         reason: "insufficient_data"

    2) Hard kill
       - Si spend >= MIN_SPEND_FOR_DECISION y roas < HARD_KILL_ROAS
         → action="kill", reason="roas_below_hard_threshold"

    3) Soft kill / pause
       - Si HARD_KILL_ROAS <= roas < SOFT_KILL_ROAS
         → action="pause", reason="roas_between_hard_and_soft_threshold"

    4) Ok
       - Si roas >= SOFT_KILL_ROAS
         → action="continue", reason="roas_acceptable"

    Esta función es totalmente pura y determinista:
    misma entrada → misma salida, sin tocar estado global.
    """
    if spend < Decimal("0"):
        raise ValueError("spend no puede ser negativo")

    roas_clamped = _clamp_roas(roas)

    # 1) Data insuficiente
    if spend < MIN_SPEND_FOR_DECISION:
        return KillDecision(
            action="continue",
            reason="insufficient_data",
        )

    # 2) Hard kill
    if roas_clamped < HARD_KILL_ROAS:
        return KillDecision(
            action="kill",
            reason="roas_below_hard_threshold",
        )

    # 3) Soft kill
    if HARD_KILL_ROAS <= roas_clamped < SOFT_KILL_ROAS:
        return KillDecision(
            action="pause",
            reason="roas_between_hard_and_soft_threshold",
        )

    # 4) Ok
    return KillDecision(
        action="continue",
        reason="roas_acceptable",
    )
