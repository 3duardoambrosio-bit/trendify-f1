from datetime import datetime, timedelta

from intelligence.early_warning import (
    EarlyWarningSignal,
    generate_early_warning,
)


def _build_decreasing_series() -> list[tuple[datetime, float]]:
    """
    Serie que va cayendo día a día.
    Ejemplo típico: ROAS deteriorándose.
    """
    start = datetime(2024, 1, 1)
    # 2.0, 1.6, 1.2, 0.8, 0.4 ...
    return [
        (start + timedelta(days=i), 2.0 - 0.4 * i)
        for i in range(5)
    ]


def _build_increasing_series() -> list[tuple[datetime, float]]:
    """
    Serie que sube día a día.
    Ejemplo típico: CPA aumentando (malo si lo vemos 'above').
    """
    start = datetime(2024, 1, 1)
    # 10, 12, 14, 16, 18 ...
    return [
        (start + timedelta(days=i), 10.0 + 2.0 * i)
        for i in range(5)
    ]


def test_generate_early_warning_critical_below_threshold() -> None:
    """
    Serie claramente decreciente que ya está por debajo del umbral.
    Esperamos una señal CRITICAL con days_to_threshold = 0.
    """
    series = _build_decreasing_series()
    # Umbral 1.0, la serie termina en 0.4 -> ya por debajo
    signal = generate_early_warning(
        metric="roas",
        values=series,
        threshold=1.0,
        direction="below",
        max_horizon_days=7,
    )

    assert signal is not None
    assert isinstance(signal, EarlyWarningSignal)
    assert signal.level == "critical"
    assert signal.days_to_threshold == 0
    assert signal.metric == "roas"
    assert "roas" in signal.message


def test_generate_early_warning_none_when_moving_away() -> None:
    """
    Si la tendencia va en la dirección contraria al riesgo,
    no debe generarse señal.
    """
    series = _build_increasing_series()
    # Preguntamos "below" pero la serie sube -> no debería cruzar hacia abajo
    signal = generate_early_warning(
        metric="roas",
        values=series,
        threshold=5.0,
        direction="below",
        max_horizon_days=7,
    )

    assert signal is None
