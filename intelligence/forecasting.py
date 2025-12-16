from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple
import math


TimeSeriesPoint = Tuple[datetime, float]


@dataclass(frozen=True)
class TrendAnalysis:
    direction: str  # "increasing" | "decreasing" | "stable"
    slope: float    # cambio por día
    confidence: float
    days_to_threshold: Optional[int]


@dataclass(frozen=True)
class ForecastPoint:
    date: datetime
    predicted_value: float
    lower_bound: float
    upper_bound: float


def _prepare_xy(values: Sequence[TimeSeriesPoint]) -> Tuple[datetime, List[float], List[float]]:
    """
    Convierte una serie temporal en pares (x, y) donde:
    - x: días desde la primera fecha
    - y: valor en float
    """
    base_date = values[0][0]
    xs: List[float] = []
    ys: List[float] = []

    for dt, val in values:
        delta_days = (dt - base_date).total_seconds() / 86400.0
        xs.append(delta_days)
        ys.append(float(val))

    return base_date, xs, ys


def _linear_regression(
    values: Sequence[TimeSeriesPoint],
) -> Tuple[float, float, float, int, Optional[datetime]]:
    """
    Regresión lineal por mínimos cuadrados.

    Devuelve:
    - slope: pendiente (valor por día)
    - intercept
    - r2: coeficiente de determinación en [0, 1]
    - n: número de puntos
    - base_date: primera fecha de la serie (para reconstruir x futuros)
    """
    if not values:
        return 0.0, 0.0, 0.0, 0, None

    base_date, xs, ys = _prepare_xy(values)
    n = len(xs)

    if n == 1:
        return 0.0, ys[0], 0.0, n, base_date

    x_mean = sum(xs) / float(n)
    y_mean = sum(ys) / float(n)

    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0.0:
        slope = 0.0
    else:
        slope = num / den

    intercept = y_mean - slope * x_mean

    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    if ss_tot <= 0.0:
        r2 = 0.0
    else:
        r2 = max(0.0, min(1.0, 1.0 - ss_res / ss_tot))

    return slope, intercept, r2, n, base_date


def calculate_linear_trend(values: Sequence[TimeSeriesPoint]) -> TrendAnalysis:
    """
    Calcula la tendencia de una serie temporal:
    - dirección: increasing / decreasing / stable
    - slope: cambio por día
    - confidence: mezcla de R^2 y tamaño de muestra
    """
    if not values:
        return TrendAnalysis(
            direction="stable",
            slope=0.0,
            confidence=0.0,
            days_to_threshold=None,
        )

    slope, intercept, r2, n, _ = _linear_regression(values)

    eps = 1e-9
    if slope > eps:
        direction = "increasing"
    elif slope < -eps:
        direction = "decreasing"
    else:
        direction = "stable"

    if n <= 1:
        confidence = 0.0
    else:
        size_factor = min(1.0, n / 10.0)
        confidence = max(0.0, min(1.0, r2 * size_factor))

    return TrendAnalysis(
        direction=direction,
        slope=slope,
        confidence=confidence,
        days_to_threshold=None,
    )


def forecast_next_days(
    values: Sequence[TimeSeriesPoint],
    days: int = 7,
) -> List[ForecastPoint]:
    """
    Proyecta los próximos `days` puntos usando la tendencia lineal.

    Retorna una lista de ForecastPoint con:
    - date futura
    - predicted_value
    - intervalo [lower_bound, upper_bound] usando una banda 2σ
    """
    if not values or days <= 0:
        return []

    slope, intercept, r2, n, base_date = _linear_regression(values)
    last_date = values[-1][0]

    # Estimación de la varianza residual para bandas de predicción
    if n >= 3 and base_date is not None:
        _, xs, ys = _prepare_xy(values)
        y_hat_vals = [slope * x + intercept for x in xs]
        ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(ys, y_hat_vals))
        dof = max(n - 2, 1)
        mse = ss_res / float(dof)
        std_err = math.sqrt(mse)
    else:
        std_err = 0.0

    points: List[ForecastPoint] = []

    for i in range(1, days + 1):
        future_date = last_date + timedelta(days=i)
        if base_date is not None:
            x = (future_date - base_date).total_seconds() / 86400.0
        else:
            x = float(i)

        pred = slope * x + intercept
        lower = pred - 2.0 * std_err
        upper = pred + 2.0 * std_err

        points.append(
            ForecastPoint(
                date=future_date,
                predicted_value=pred,
                lower_bound=lower,
                upper_bound=upper,
            )
        )

    return points


def days_until_threshold(
    values: Sequence[TimeSeriesPoint],
    threshold: float,
    direction: str = "below",
) -> Optional[int]:
    """
    Estima en cuántos días la serie cruzará un umbral.

    direction:
    - "below": ¿cuándo bajará de threshold?
    - "above": ¿cuándo superará threshold?

    Retorna:
    - 0 si ya está en el lado deseado.
    - None si a la tendencia actual no parece que cruce.
    - Un entero >= 0 con los días estimados (redondeo hacia arriba).
    """
    if direction not in ("below", "above"):
        raise ValueError("direction must be 'below' or 'above'")

    if not values:
        return None

    slope, intercept, r2, n, base_date = _linear_regression(values)
    if n <= 1 or base_date is None:
        return None

    current_value = float(values[-1][1])

    if direction == "below":
        if current_value <= threshold:
            return 0
        if slope >= 0.0:
            return None
    else:  # direction == "above"
        if current_value >= threshold:
            return 0
        if slope <= 0.0:
            return None

    # Convertimos la última fecha a x_last en días
    x_last = (values[-1][0] - base_date).total_seconds() / 86400.0

    if slope == 0.0:
        return None

    # threshold = slope * x + intercept  -> resolvemos por x
    x_threshold = (threshold - intercept) / slope
    days = x_threshold - x_last

    if days < 0:
        return None

    return max(0, int(math.ceil(days)))
