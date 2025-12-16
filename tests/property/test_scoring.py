import math

import pytest
from hypothesis import given, strategies as st

from core.scoring import BayesianScore


# Estrategias de Hypothesis para generar inputs válidos
valid_mean = st.floats(
    min_value=0.0,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
)

valid_confidence = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

valid_sample_size = st.integers(min_value=0, max_value=100_000)

# Para la mayoría de las pruebas NO necesitamos tocar los extremos exactos.
# Los extremos 0 y 100 se prueban aparte en un test específico.
valid_threshold = st.floats(
    min_value=1.0,
    max_value=99.0,
    allow_nan=False,
    allow_infinity=False,
)


def test_bayesian_score_basic_invariants() -> None:
    score = BayesianScore(mean=75.0, confidence=0.8, sample_size=10)

    assert score.mean == 75.0
    assert score.confidence == 0.8
    assert score.sample_size == 10

    assert 0.0 <= score.uncertainty <= 1.0
    assert 0.0 <= score.range_low <= score.range_high <= 100.0


@given(
    mean=valid_mean,
    confidence=valid_confidence,
    sample_size=valid_sample_size,
)
def test_bayesian_score_property_invariants(
    mean: float,
    confidence: float,
    sample_size: int,
) -> None:
    """
    Para cualquier combinación válida de parámetros:
    - El score respeta el rango [0, 100].
    - La confianza y la incertidumbre están en [0, 1].
    - El rango [range_low, range_high] es válido y acotado.
    """
    score = BayesianScore(mean=mean, confidence=confidence, sample_size=sample_size)

    assert 0.0 <= score.mean <= 100.0
    assert 0.0 <= score.confidence <= 1.0
    assert 0.0 <= score.uncertainty <= 1.0
    assert score.sample_size >= 0

    assert 0.0 <= score.range_low <= score.range_high <= 100.0


@given(
    mean=valid_mean,
    confidence=valid_confidence,
    sample_size=valid_sample_size,
    threshold=valid_threshold,
)
def test_probability_above_is_between_zero_and_one(
    mean: float,
    confidence: float,
    sample_size: int,
    threshold: float,
) -> None:
    """
    P(score > threshold) SIEMPRE debe estar en [0, 1].
    """
    score = BayesianScore(mean=mean, confidence=confidence, sample_size=sample_size)
    prob = score.probability_above(threshold)

    assert 0.0 <= prob <= 1.0


def test_probability_above_extremes() -> None:
    """
    Casos límite en los bordes del dominio.
    Estos extremos se prueban explícitamente:
    - threshold <= 0  -> prob = 1.0
    - threshold >= 100 -> prob = 0.0
    """
    high_score = BayesianScore(mean=95.0, confidence=0.9, sample_size=100)
    low_score = BayesianScore(mean=10.0, confidence=0.9, sample_size=100)

    # Threshold muy bajo → prob = 1.0
    assert high_score.probability_above(0.0) == pytest.approx(1.0)
    assert low_score.probability_above(0.0) == pytest.approx(1.0)

    # Threshold muy alto → prob = 0.0
    assert high_score.probability_above(100.0) == pytest.approx(0.0)
    assert low_score.probability_above(100.0) == pytest.approx(0.0)


@given(
    confidence=st.floats(
        min_value=0.0,
        max_value=0.05,
        allow_nan=False,
        allow_infinity=False,
    ),
    # Aquí usamos thresholds "razonables", lejos de 0 y 100.
    threshold=st.floats(
        min_value=10.0,
        max_value=90.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_low_confidence_converges_to_half(
    confidence: float,
    threshold: float,
) -> None:
    """
    Con confianza muy baja, la probabilidad debe acercarse a 0.5
    para thresholds razonables en el rango [10, 90].
    No verificamos extremos; eso se cubre en test_probability_above_extremes.
    """
    score = BayesianScore(mean=50.0, confidence=confidence, sample_size=0)
    prob = score.probability_above(threshold)

    # No exigimos igualdad perfecta, sólo que esté en una banda razonable.
    assert 0.2 <= prob <= 0.8


@given(
    confidence=st.floats(
        min_value=0.8,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_monotonicity_with_threshold(confidence: float) -> None:
    """
    Para una mean fija y confianza alta:
    - Si el threshold sube, la probabilidad de estar por encima
      no puede aumentar.
    """
    score = BayesianScore(mean=70.0, confidence=confidence, sample_size=50)

    p_low = score.probability_above(40.0)
    p_mid = score.probability_above(70.0)
    p_high = score.probability_above(90.0)

    assert 0.0 <= p_high <= p_mid <= p_low <= 1.0
