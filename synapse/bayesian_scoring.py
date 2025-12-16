from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from typing import Iterable, Sequence


@dataclass(frozen=True)
class BayesianScore:
    """
    Scoring bayesiano simplificado pero serio.

    - mean: media posterior de éxito (0–1).
    - confidence: qué tan confiable es la estimación (0–1).
    - probability_success: P(θ >= threshold | datos) en [0, 1].

    Esta clase NO asume nada de dropshipping; sólo sabe de probabilidades.
    El caller decide qué significa "éxito" y cómo se traduce a p en [0, 1].
    """

    mean: float
    confidence: float
    probability_success: float
    threshold: float

    def to_human_sentence(self) -> str:
        """
        Resumen tipo "explicabilidad en una frase".
        Ejemplo:
        "Esperamos que el producto tenga éxito con prob. ~78% (score medio 0.72, confianza 0.81)."
        """
        p_pct = round(self.probability_success * 100)
        mean_pct = round(self.mean * 100)
        conf_pct = round(self.confidence * 100)
        return (
            f"Esperamos que supere el umbral ({int(self.threshold * 100)}%) "
            f"con probabilidad ≈{p_pct}%, score medio {mean_pct}%, "
            f"confianza {conf_pct}%."
        )


def _clip_01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normal_cdf(z: float) -> float:
    """
    CDF de Normal(0,1) usando erf, sin dependencias externas.

    Φ(z) = 0.5 * [1 + erf(z / sqrt(2))]
    """
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def bayesian_score_from_probability(
    base_prob: float,
    data_points: int,
    threshold: float = 0.7,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    max_n_for_confidence: int = 1000,
) -> BayesianScore:
    """
    Modelo bayesiano simple con prior Beta y aproximación normal.

    Pensado para escenarios tipo:
      - base_prob: "creemos que este setup tiene prob. 0.65 de ser winner"
      - data_points: número efectivo de observaciones (clicks, visitas, etc.)

    Interpreta:
      - prior ~ Beta(prior_alpha, prior_beta)
      - evidencia: data_points * base_prob "éxitos" y el resto "fracasos"
      - posterior: Beta(alpha_post, beta_post)
      - mean: media posterior
      - probability_success: P(θ >= threshold | posterior) vía aproximación normal
      - confidence: función creciente en (alpha_post + beta_post), truncada a 1.
    """
    if data_points <= 0:
        # Sin datos: devolvemos algo neutro pero consistente
        mean = _clip_01(base_prob)
        return BayesianScore(
            mean=mean,
            confidence=0.0,
            probability_success=0.5,
            threshold=threshold,
        )

    p = _clip_01(base_prob)
    successes = p * float(data_points)
    fails = (1.0 - p) * float(data_points)

    alpha_post = prior_alpha + successes
    beta_post = prior_beta + fails
    n_post = alpha_post + beta_post

    # Media posterior de Beta
    mean = alpha_post / n_post

    # Varianza de Beta(a, b): ab / ((a+b)^2 (a+b+1))
    var = (alpha_post * beta_post) / ((n_post * n_post) * (n_post + 1.0))
    if var <= 0.0:
        # Degenerado: sin varianza
        probability_success = 1.0 if mean >= threshold else 0.0
    else:
        sigma = sqrt(var)
        # P(θ >= threshold) ≈ 1 - Φ((threshold - mean) / sigma)
        z = (threshold - mean) / sigma
        probability_success = 1.0 - _normal_cdf(z)

    probability_success = _clip_01(probability_success)

    # Confianza: función suave y creciente en n_post
    # n_post ~ 0         -> confidence ≈ 0
    # n_post >= max_n    -> confidence ≈ 1
    confidence_raw = n_post / float(max_n_for_confidence)
    confidence = _clip_01(confidence_raw)

    return BayesianScore(
        mean=float(_clip_01(mean)),
        confidence=float(confidence),
        probability_success=float(probability_success),
        threshold=float(threshold),
    )


def combine_feature_scores(
    scores: Sequence[float],
    weights: Sequence[float] | None = None,
) -> float:
    """
    Combina varios scores de features en un solo "base_prob" en [0, 1],
    usando promedio ponderado.

    - scores: valores en [0, 1]
    - weights: pesos no negativos (si None, usa uniforme)

    Esto NO es bayesiano todavía, sólo una forma limpia de consolidar señales.
    """
    if not scores:
        return 0.0

    clipped = [_clip_01(float(s)) for s in scores]

    if weights is None:
        return sum(clipped) / float(len(clipped))

    if len(weights) != len(clipped):
        raise ValueError("scores y weights deben tener la misma longitud")

    w = [max(0.0, float(x)) for x in weights]
    total_w = sum(w)
    if total_w <= 0.0:
        return sum(clipped) / float(len(clipped))

    return sum(s * wi for s, wi in zip(clipped, w)) / total_w
