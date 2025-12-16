from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence, Optional, Tuple, List


@dataclass(frozen=True)
class Trend:
    """
    Tendencia lineal de una serie temporal corta.

    x = 0, 1, ..., n-1
    y = valores observados (por ejemplo, ROAS diario).

    slope      : cambio esperado por unidad de tiempo.
    intercept  : valor estimado en x=0.
    r2         : coeficiente de determinación (0–1) o None si no aplica.
    n_points   : número de observaciones usadas.
    """

    slope: float
    intercept: float
    r2: Optional[float]
    n_points: int


@dataclass(frozen=True)
class ForecastPoint:
    """
    Predicción puntual + intervalo para una fecha futura.

    predicted_value : valor central estimado.
    lower_bound     : límite inferior del intervalo de predicción.
    upper_bound     : límite superior del intervalo de predicción.
    days_ahead      : cuántos días hacia adelante estamos prediciendo
                      respecto al último punto de la serie.
    """

    predicted_value: float
    lower_bound: float
    upper_bound: float
    days_ahead: float


def _basic_stats(values: Sequence[float]) -> Tuple[float, float]:
    """
    Retorna (mean, variance) de una secuencia de floats.
    Varianza corregida con (n-1) en el denominador para n>=2.
    """
    n = len(values)
    if n == 0:
        raise ValueError("No se pueden calcular estadísticas de una secuencia vacía")

    mean = sum(values) / float(n)
    if n == 1:
        return mean, 0.0

    var = sum((v - mean) ** 2 for v in values) / float(n - 1)
    return mean, var


def fit_linear_trend(values: Sequence[float]) -> Trend:
    """
    Ajusta una tendencia lineal y = m*x + b sobre la serie.

    - x = 0..n-1
    - y = values[x]

    Diseñado para ventanas cortas (3–30 puntos), típico de campañas al inicio.

    Si hay menos de 2 puntos, usamos slope=0 y estimamos intercept como el último valor.
    """
    n = len(values)
    if n == 0:
        raise ValueError("Se requiere al menos un dato para estimar tendencia")

    if n == 1:
        y = float(values[0])
        return Trend(slope=0.0, intercept=y, r2=None, n_points=1)

    xs = [float(i) for i in range(n)]
    ys = [float(v) for v in values]

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))

    denom = n * sum_xx - sum_x ** 2
    if denom == 0.0:
        # Serie degenerada (todos los x iguales, que en teoría no pasa aquí)
        mean_y = sum_y / float(n)
        return Trend(slope=0.0, intercept=mean_y, r2=None, n_points=n)

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / float(n)

    # Calculamos R^2 como 1 - SSE/SST
    y_mean = sum_y / float(n)
    y_hat = [slope * x + intercept for x in xs]
    sse = sum((y - yh) ** 2 for y, yh in zip(ys, y_hat))
    sst = sum((y - y_mean) ** 2 for y in ys)

    if sst <= 0.0:
        r2: Optional[float] = None
    else:
        r2 = max(0.0, min(1.0, 1.0 - sse / sst))

    return Trend(
        slope=float(slope),
        intercept=float(intercept),
        r2=r2,
        n_points=n,
    )


def forecast_with_interval(
    values: Sequence[float],
    days_ahead: float = 1.0,
    confidence_z: float = 1.96,
) -> ForecastPoint:
    """
    Predice el valor futuro de la serie y devuelve un intervalo de predicción.

    - Ajusta una recta y = m*x + b.
    - Usa la desviación estándar de los residuos como sigma.
    - Intervalo ≈ y_hat ± z * sigma.

    Para n < 3, el intervalo se vuelve más ancho por falta de datos.
    """
    if not values:
        raise ValueError("Se requiere al menos un dato para pronosticar")

    trend = fit_linear_trend(values)
    n = trend.n_points

    # Índice del último punto observado
    last_x = float(n - 1)
    target_x = last_x + float(days_ahead)

    predicted = trend.slope * target_x + trend.intercept

    # Estimamos sigma a partir de los residuos
    if n >= 3:
        xs = [float(i) for i in range(n)]
        ys = [float(v) for v in values]
        residuals = [
            y - (trend.slope * x + trend.intercept) for x, y in zip(xs, ys)
        ]
        _, var_res = _basic_stats(residuals)
        sigma = sqrt(var_res)
    else:
        # Con pocos datos, inflamos la incertidumbre
        _, var_y = _basic_stats([float(v) for v in values])
        sigma = sqrt(var_y) if var_y > 0.0 else 0.0

    margin = confidence_z * sigma
    lower = predicted - margin
    upper = predicted + margin

    return ForecastPoint(
        predicted_value=float(predicted),
        lower_bound=float(lower),
        upper_bound=float(upper),
        days_ahead=float(days_ahead),
    )


def estimate_days_until_threshold(
    values: Sequence[float],
    threshold: float,
) -> Optional[float]:
    """
    Estima cuántos días faltan para que la serie cruce el `threshold`
    según la tendencia lineal.

    - Si la tendencia nunca cruza de forma lógica (ej. slope ≈ 0 lejos del threshold),
      retorna None.
    - Si ya estamos por debajo (en caso de caída) o por encima (en caso de subida),
      puede devolver 0.0.

    Uso típico:
      - ROAS -> threshold = 1.0
      - CPC  -> threshold = cierto máximo tolerable
    """
    if not values:
        return None

    trend = fit_linear_trend(values)
    n = trend.n_points
    last_value = float(values[-1])

    # Slope ~ 0: la serie no se mueve significativamente
    if abs(trend.slope) < 1e-9:
        # Si ya está "en la zona mala", decimos que el límite ya se cruzó
        if last_value <= threshold:
            return 0.0
        # Si está por encima y no hay tendencia, no sabemos cuándo bajará
        return None

    # Resolvemos threshold = m*x + b => x = (threshold - b) / m
    x_cross = (threshold - trend.intercept) / trend.slope
    current_x = float(n - 1)
    days = x_cross - current_x

    # Si el cruce fue en el pasado
    if days < 0.0:
        return 0.0

    return float(days)
