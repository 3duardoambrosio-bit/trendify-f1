from datetime import datetime, timedelta

from intelligence.forecasting import (
    TrendAnalysis,
    ForecastPoint,
    calculate_linear_trend,
    forecast_next_days,
    days_until_threshold,
)


def _build_increasing_series() -> list[tuple[datetime, float]]:
    start = datetime(2024, 1, 1)
    # y = 10 + 2 * t (t en días)
    return [
        (start + timedelta(days=i), 10.0 + 2.0 * i)
        for i in range(5)
    ]


def _build_decreasing_series() -> list[tuple[datetime, float]]:
    start = datetime(2024, 1, 1)
    # y = 20 - 1 * t
    return [
        (start + timedelta(days=i), 20.0 - 1.0 * i)
        for i in range(5)
    ]


def test_calculate_linear_trend_increasing() -> None:
    values = _build_increasing_series()
    trend = calculate_linear_trend(values)

    assert isinstance(trend, TrendAnalysis)
    assert trend.direction == "increasing"
    assert trend.slope > 0.0
    assert 0.0 <= trend.confidence <= 1.0
    assert trend.days_to_threshold is None


def test_forecast_next_days_shape_and_monotonic() -> None:
    values = _build_increasing_series()
    points = forecast_next_days(values, days=3)

    assert len(points) == 3
    assert all(isinstance(p, ForecastPoint) for p in points)

    # Fechas estrictamente crecientes
    assert all(points[i].date < points[i + 1].date for i in range(len(points) - 1))

    # Como la serie es claramente creciente, el forecast también debe ser creciente
    preds = [p.predicted_value for p in points]
    assert preds[0] < preds[1] < preds[2]


def test_days_until_threshold_above_and_none_when_moving_away() -> None:
    # Serie creciente, queremos saber cuándo supera cierto threshold
    increasing = _build_increasing_series()
    days_above = days_until_threshold(
        increasing,
        threshold=20.0,
        direction="above",
    )

    assert days_above is not None
    assert days_above >= 1

    # Serie decreciente, preguntamos por "above" un valor alto -> nunca lo cruza
    decreasing = _build_decreasing_series()
    days_never = days_until_threshold(
        decreasing,
        threshold=25.0,
        direction="above",
    )

    assert days_never is None
