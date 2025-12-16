from __future__ import annotations

from synapse.bayesian_scoring import (
    BayesianScore,
    bayesian_score_from_probability,
    combine_feature_scores,
)

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st  # type: ignore[assignment]


@given(
    base_prob=st.floats(min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    data_points=st.integers(min_value=1, max_value=10_000),
    threshold=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
)
def test_bayesian_score_invariants(
    base_prob: float,
    data_points: int,
    threshold: float,
) -> None:
    score = bayesian_score_from_probability(
        base_prob=base_prob,
        data_points=data_points,
        threshold=threshold,
    )

    # Todos los campos clave deben estar dentro de [0, 1]
    assert 0.0 <= score.mean <= 1.0
    assert 0.0 <= score.confidence <= 1.0
    assert 0.0 <= score.probability_success <= 1.0
    assert 0.1 <= score.threshold <= 0.9


def test_more_data_increases_confidence() -> None:
    """
    A igual base_prob y threshold, más datos => mayor o igual confianza.
    """
    s1 = bayesian_score_from_probability(
        base_prob=0.7,
        data_points=10,
        threshold=0.6,
    )
    s2 = bayesian_score_from_probability(
        base_prob=0.7,
        data_points=1000,
        threshold=0.6,
    )

    assert s2.confidence >= s1.confidence


def test_probability_success_behaves_with_threshold() -> None:
    """
    Si p_base es alto y threshold bajo, P(éxito) debe ser alta.
    Si p_base es bajo y threshold alto, P(éxito) debe ser baja.
    """
    high = bayesian_score_from_probability(
        base_prob=0.9,
        data_points=500,
        threshold=0.6,
    )
    low = bayesian_score_from_probability(
        base_prob=0.2,
        data_points=500,
        threshold=0.8,
    )

    assert high.probability_success > 0.7
    assert low.probability_success < 0.3


def test_combine_feature_scores_basic() -> None:
    scores = [0.2, 0.8, 0.6]
    combined = combine_feature_scores(scores)
    assert 0.0 <= combined <= 1.0
    # promedio simple de 0.2, 0.8, 0.6 = 0.53(3)
    assert 0.4 < combined < 0.8

    weighted = combine_feature_scores(scores, weights=[1.0, 3.0, 1.0])
    # Debería acercarse más al 0.8
    assert weighted > combined
