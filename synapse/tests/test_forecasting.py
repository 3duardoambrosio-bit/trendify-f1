from __future__ import annotations

from synapse.forecasting import (
    fit_linear_trend,
    forecast_with_interval,
    estimate_days_until_threshold,
)

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st  # type: ignore[assignment]


@given(
    start=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    slope=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_fit_linear_trend_recovers_sign_of_slope(start: float, slope: float) -> None:
    """
    Para una serie perfectamente lineal, el signo de la pendiente
    estimada debe coincidir con el de la pendiente real.
    """
    n = 10
    ys = [start + slope * i for i in range(n)]

    trend = fit_linear_trend(ys)

    if slope > 1e-6:
        assert trend.slope > 0
    elif slope < -1e-6:
        assert trend.slope < 0
    else:
        assert abs(trend.slope) < 1e-3


def test_forecast_with_interval_constant_series() -> None:
    """
    En una serie casi constante, la predicción debe ser cercana
    al valor medio y el intervalo no debe explotar.
    """
    ys = [2.0, 2.1, 1.9, 2.05, 1.95]
    fc = forecast_with_interval(ys, days_ahead=2.0)

    assert 1.5 < fc.predicted_value < 2.5
    assert fc.lower_bound < fc.predicted_value < fc.upper_bound
    # El intervalo no debería ser un rango absurdo
    assert fc.upper_bound - fc.lower_bound < 5.0


def test_estimate_days_until_threshold_decreasing_series() -> None:
    """
    En una serie claramente decreciente por encima del threshold,
    los días hasta cruzar el límite deben ser finitos y positivos.
    """
    ys = [3.0, 2.5, 2.0, 1.5]
    threshold = 1.0

    days = estimate_days_until_threshold(ys, threshold)

    assert days is not None
    assert days >= 0.0
    # No debería decir que faltan 1000 días...
    assert days < 100.0
