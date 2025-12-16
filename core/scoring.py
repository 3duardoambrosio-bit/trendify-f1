from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Final


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + exp(-z))
    ez = exp(z)
    return ez / (1.0 + ez)


@dataclass(frozen=True)
class BayesianScore:
    """
    Score con incertidumbre explícita (F1).

    mean: 0..100
    confidence: 0..1
    sample_size: >=0

    uncertainty = 1 - confidence
    range_low/high: rango [0..100] basado en incertidumbre
    probability_above(threshold): P(score > threshold) con mezcla por confianza
      - confidence ~ 0 => ~0.5 (neutral) *excepto extremos del dominio*
      - confidence ~ 1 => más “nítido”
    """

    mean: float
    confidence: float
    sample_size: int

    _SPREAD_POINTS: Final[float] = 20.0
    _EPS: Final[float] = 1e-6

    def __post_init__(self) -> None:
        m = _clip(float(self.mean), 0.0, 100.0)
        c = _clip(float(self.confidence), 0.0, 1.0)
        n = int(self.sample_size)
        if n < 0:
            n = 0

        object.__setattr__(self, "mean", m)
        object.__setattr__(self, "confidence", c)
        object.__setattr__(self, "sample_size", n)

    @property
    def uncertainty(self) -> float:
        return 1.0 - self.confidence

    @property
    def _spread(self) -> float:
        return self._SPREAD_POINTS * self.uncertainty

    @property
    def range_low(self) -> float:
        return max(0.0, self.mean - self._spread)

    @property
    def range_high(self) -> float:
        return min(100.0, self.mean + self._spread)

    def probability_above(self, threshold: float) -> float:
        t = float(threshold)

        # 🔒 Contrato de tests / bordes del dominio:
        # score ∈ [0,100] => P(score > t) = 1 si t<=0; =0 si t>=100
        if t <= 0.0:
            return 1.0
        if t >= 100.0:
            return 0.0

        t = _clip(t, 0.0, 100.0)

        # Confianza 0 => neutral (en el interior del dominio)
        if self.confidence <= 0.0:
            return 0.5

        spread = max(self._spread, self._EPS)
        z = (self.mean - t) / spread
        base = _sigmoid(z)

        prob = 0.5 + self.confidence * (base - 0.5)
        return _clip(float(prob), 0.0, 1.0)