from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence, Tuple

from .forecasting import (
    TrendAnalysis,
    calculate_linear_trend,
    days_until_threshold,
)

TimeSeriesPoint = Tuple[datetime, float]


@dataclass(frozen=True)
class EarlyWarningSignal:
    """
    Señal temprana sobre un métrico de performance.

    Ejemplos de métricos:
    - roas
    - cpa
    - ctr
    - margin

    La idea es responder preguntas tipo:
    "A este ritmo, ¿en cuántos días mi ROAS va a caer por debajo de 1.0?"
    """

    metric: str
    level: str  # "info" | "warning" | "critical"
    message: str
    days_to_threshold: Optional[int]
    direction: str
    slope: float
    threshold: float
    current_value: float


def generate_early_warning(
    metric: str,
    values: Sequence[TimeSeriesPoint],
    threshold: float,
    direction: str = "below",
    max_horizon_days: int = 7,
) -> Optional[EarlyWarningSignal]:
    """
    Genera una señal early-warning para un métrico dado.

    Parámetros:
    - metric: nombre del métrico ("roas", "cpa", etc.)
    - values: serie temporal [(datetime, valor), ...]
    - threshold: umbral crítico (ej. 1.0 para ROAS)
    - direction:
        - "below": el riesgo es caer por debajo del threshold
        - "above": el riesgo es superar el threshold
    - max_horizon_days: horizonte máximo para considerar warning

    Reglas:
    - Si la serie está vacía → None.
    - Usa la tendencia lineal y days_until_threshold para estimar cruce.
    - Clasifica:
        - None         → sin señal (no parece cruzar)
        - 0-2 días     → "critical"
        - 3-horizonte  → "warning"
        - > horizonte  → "info"
    """
    if not values:
        return None

    if direction not in ("below", "above"):
        raise ValueError("direction must be 'below' or 'above'")

    trend: TrendAnalysis = calculate_linear_trend(values)
    days: Optional[int] = days_until_threshold(
        values,
        threshold=threshold,
        direction=direction,
    )

    current_value = float(values[-1][1])

    if days is None:
        # A la tendencia actual, no parece que vayamos a cruzar el umbral.
        return None

    # Clasificación por urgencia
    if days <= 2:
        level = "critical"
    elif days <= max_horizon_days:
        level = "warning"
    else:
        level = "info"

    # Mensaje humano orientado a dashboard / bitácora
    if direction == "below":
        dir_text = "por debajo"
    else:
        dir_text = "por encima"

    message = (
        f"{metric}: se proyecta cruzar {dir_text} de {threshold:.2f} en ~{days} días "
        f"(valor actual {current_value:.2f}, slope={trend.slope:.4f}/día, "
        f"tendencia={trend.direction}, confianza={trend.confidence:.2f})."
    )

    return EarlyWarningSignal(
        metric=metric,
        level=level,
        message=message,
        days_to_threshold=days,
        direction=trend.direction,
        slope=trend.slope,
        threshold=threshold,
        current_value=current_value,
    )
