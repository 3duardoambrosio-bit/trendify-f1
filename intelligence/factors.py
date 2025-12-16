from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence
from decimal import Decimal


Number = float | int | Decimal


def _to_float(value: Any) -> Optional[float]:
    """
    Intenta convertir a float valores numéricos (int, float, Decimal).
    Si no se puede, retorna None.
    """
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        # Intento defensivo por si llegan strings numéricos
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class FactorAnalysis:
    """
    Resultado de comparar un factor entre productos exitosos vs fallidos.
    """

    factor: str
    avg_in_successful: float
    avg_in_failed: float
    difference: float
    sample_size: int

    @property
    def is_significant(self) -> bool:
        """
        Regla fundacional:

        - diferencia relativa > 20%
        - sample_size >= 5
        """
        denom = max(self.avg_in_successful, self.avg_in_failed, 0.01)
        relative_diff = abs(self.difference) / denom
        return relative_diff > 0.20 and self.sample_size >= 5

    @property
    def direction(self) -> str:
        """
        Interpreta en qué sentido parece moverse el factor:

        - "higher_is_better"
        - "lower_is_better"
        - "neutral" (si prácticamente no hay diferencia)
        """
        if abs(self.difference) < 1e-9:
            return "neutral"
        return "higher_is_better" if self.avg_in_successful > self.avg_in_failed else "lower_is_better"


def _iter_numeric_field(
    products: Iterable[Dict[str, Any]],
    field: str,
) -> List[float]:
    values: List[float] = []
    for p in products:
        raw = p.get(field)
        val = _to_float(raw)
        if val is not None:
            values.append(val)
    return values


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def analyze_success_factors(
    products: List[Dict[str, Any]],
    success_field: str = "was_successful",
    factors: Optional[List[str]] = None,
) -> List[FactorAnalysis]:
    """
    Compara factores numéricos entre productos exitosos vs fallidos.

    - products: lista de dicts con al menos success_field y los factores.
    - success_field: clave booleana o truthy/falsy que indica éxito.
    - factors: lista de claves a analizar. Si None, se infiere de las
      keys del primer producto, excluyendo success_field.

    Retorna una lista de FactorAnalysis ordenada por |difference| desc.
    """
    if not products:
        return []

    if factors is None:
        # inferimos factores numéricos potenciales de la primera fila
        first = products[0]
        factors = [
            k
            for k in first.keys()
            if k != success_field
        ]

    successful = [p for p in products if bool(p.get(success_field))]
    failed = [p for p in products if not bool(p.get(success_field))]

    analyses: List[FactorAnalysis] = []

    for factor in factors:
        succ_vals = _iter_numeric_field(successful, factor)
        fail_vals = _iter_numeric_field(failed, factor)

        if not succ_vals and not fail_vals:
            # Factor no numérico o vacío: lo saltamos
            continue

        avg_success = _mean(succ_vals)
        avg_failed = _mean(fail_vals)
        diff = avg_success - avg_failed
        sample_size = len(succ_vals) + len(fail_vals)

        analyses.append(
            FactorAnalysis(
                factor=factor,
                avg_in_successful=avg_success,
                avg_in_failed=avg_failed,
                difference=diff,
                sample_size=sample_size,
            )
        )

    # Ordenamos por magnitud de diferencia, mayor primero
    analyses.sort(key=lambda fa: abs(fa.difference), reverse=True)
    return analyses


def generate_insights(analyses: List[FactorAnalysis]) -> List[str]:
    """
    Genera insights legibles a partir de una lista de FactorAnalysis.

    Solo se generan insights para factores "significant".
    """
    insights: List[str] = []

    for fa in analyses:
        if not fa.is_significant:
            continue

        sign = "📈" if fa.direction == "higher_is_better" else "📉"
        diff = fa.difference

        # Lo mostramos como número normal; si el caller quiere pct,
        # puede darle factores ya en porcentaje.
        msg = (
            f"{sign} {fa.factor}: productos exitosos tienen "
            f"{fa.avg_in_successful:.2f} vs {fa.avg_in_failed:.2f} en fallidos "
            f"({diff:+.2f}). [{fa.direction}, n={fa.sample_size}]"
        )
        insights.append(msg)

    return insights
