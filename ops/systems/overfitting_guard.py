from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from infra.bitacora_auto import BitacoraAuto, EntryType, BITACORA_PATH
from ops.systems.tribunal import load_exit_events  # para futuras heurísticas


# =========================
#  MODELOS
# =========================


@dataclass
class EvaluationSnapshot:
    """Snapshot mínimo de una evaluación de producto."""

    product_id: str
    composite_score: float
    quality_score: float


@dataclass
class OverfitAlert:
    """Alerta de posible overfitting en reglas."""

    type: str          # ej: "LOW_VARIANCE_SCORE"
    message: str       # texto humano
    details: Dict[str, float]


# =========================
#  HELPERS
# =========================


def load_evaluations(path: Path) -> List[EvaluationSnapshot]:
    """
    Carga de Bitácora todas las entradas de tipo product_evaluation
    y las normaliza a EvaluationSnapshot.

    Soporta dos formatos:
    - data["composite_score"], data["quality_score"]
    - data["buyer_scores"]["composite_score"]
    """
    bitacora = BitacoraAuto(path=path)
    entries = bitacora.load_entries()

    snapshots: List[EvaluationSnapshot] = []

    for entry in entries:
        if entry.entry_type != EntryType.PRODUCT_EVALUATION:
            continue

        data = entry.data or {}

        buyer_scores = data.get("buyer_scores") or {}
        composite_raw = (
            buyer_scores.get("composite_score")
            or data.get("composite_score")
            or 0.0
        )

        composite_score = float(composite_raw or 0.0)
        quality_score = float(data.get("quality_score") or 0.0)

        snapshots.append(
            EvaluationSnapshot(
                product_id=str(data.get("product_id", "unknown")),
                composite_score=composite_score,
                quality_score=quality_score,
            )
        )

    return snapshots


# =========================
#  DETECTORES DE OVERFITTING
# =========================


def _detect_low_variance_score(
    evaluations: List[EvaluationSnapshot],
    min_samples: int = 5,
    min_range: float = 0.05,
) -> Optional[OverfitAlert]:
    """
    Si todos los composite_score están casi iguales, levantamos
    alerta de LOW_VARIANCE_SCORE.

    Esto es exactamente lo que test_detects_low_variance_score espera:
    - Con 5 productos y composite_score = 0.8, 0.8, 0.8, 0.8, 0.8
      el rango será 0.0  → se debe disparar.
    - En el test de "scores diversos", el rango será grande y NO
      se debe disparar.
    """
    if len(evaluations) < min_samples:
        return None

    scores = [e.composite_score for e in evaluations]
    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score

    if score_range < min_range:
        return OverfitAlert(
            type="LOW_VARIANCE_SCORE",
            message=(
                "Las evaluaciones recientes tienen scores casi idénticos; "
                "posible overfitting de reglas de Buyer/Exit."
            ),
            details={
                "count": float(len(scores)),
                "min_score": float(min_score),
                "max_score": float(max_score),
                "range": float(score_range),
            },
        )

    return None


# (Hook para futuras heurísticas basadas en exits; de momento los tests
# solo exigen LOW_VARIANCE_SCORE, así que no hacemos nada aquí aún.)
def _detect_other_patterns(
    evaluations: List[EvaluationSnapshot],
    path: Path,
) -> List[OverfitAlert]:
    _ = evaluations
    _ = load_exit_events(path=path)  # wiring listo para Fase 2+
    return []


# =========================
#  API PRINCIPAL
# =========================


def analyze_overfitting(path: Optional[Path] = None) -> List[OverfitAlert]:
    """
    Analiza posibles señales de overfitting leyendo la Bitácora.

    - Si `path` viene en None (scripts/demo), usa BITACORA_PATH por defecto.
    - Si los tests pasan un path explícito (tmp_path), se respeta ese path.
    """
    if path is None:
        path = BITACORA_PATH

    evaluations = load_evaluations(path=path)

    alerts: List[OverfitAlert] = []

    # 1) LOW_VARIANCE_SCORE (lo que están probando los tests)
    low_var = _detect_low_variance_score(evaluations)
    if low_var:
        alerts.append(low_var)

    # 2) Otros patrones (placeholder futuro)
    alerts.extend(_detect_other_patterns(evaluations, path=path))

    return alerts
