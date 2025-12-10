from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from infra.bitacora_auto import BitacoraAuto, EntryType, BITACORA_PATH


# === MODELOS ===


@dataclass
class ExitSnapshot:
    """Snapshot mínimo de un product_exit en Bitácora."""

    product_id: str
    verdict: str
    reason: str
    roas: float
    quality_score: float


@dataclass
class FeedbackSuggestion:
    """
    Sugerencia de ajuste de reglas.

    En F1 solo tocamos ExitCriteria (kill / continue).
    """

    code: str               # id estable, ej: "exit.roas_threshold.maybe_too_strict"
    message: str            # texto humano
    details: Dict[str, float]  # métricas agregadas para contexto


# === HELPERS ===


def load_exits(path: Path) -> List[ExitSnapshot]:
    """
    Carga de Bitácora todas las entradas de tipo product_exit
    y las normaliza a ExitSnapshot.
    """
    bitacora = BitacoraAuto(path=path)
    entries = bitacora.load_entries()

    exits: List[ExitSnapshot] = []
    for entry in entries:
        if entry.entry_type != EntryType.PRODUCT_EXIT:
            continue

        data = entry.data or {}

        exits.append(
            ExitSnapshot(
                product_id=str(data.get("product_id", "unknown")),
                verdict=str(data.get("verdict", "unknown")),
                reason=str(data.get("reason", "unknown")),
                roas=float(data.get("roas", 0.0) or 0.0),
                quality_score=float(data.get("quality_score", 0.0) or 0.0),
            )
        )

    return exits


def _suggest_roas_threshold(exits: List[ExitSnapshot]) -> Optional[FeedbackSuggestion]:
    """
    Heurística F1:
    Si estamos matando muchos productos con ROAS y calidad decentes,
    probablemente el umbral de ROAS mínimo está muy alto.
    """
    kills = [e for e in exits if e.verdict == "kill"]
    if len(kills) < 3:
        return None

    avg_roas_kill = sum(e.roas for e in kills) / len(kills)
    avg_quality_kill = sum(e.quality_score for e in kills) / len(kills)

    if avg_roas_kill >= 0.9 and avg_quality_kill >= 0.7:
        return FeedbackSuggestion(
            code="exit.roas_threshold.maybe_too_strict",
            message=(
                "Muchos productos se están matando con ROAS y calidad decentes; "
                "revisa si el umbral de ROAS mínimo en ExitCriteria está demasiado alto."
            ),
            details={
                "kills": float(len(kills)),
                "avg_roas_kill": avg_roas_kill,
                "avg_quality_kill": avg_quality_kill,
            },
        )

    return None


def _suggest_continue_rules(exits: List[ExitSnapshot]) -> Optional[FeedbackSuggestion]:
    """
    Heurística F1:
    Si hay muchos 'continue' con ROAS y calidad bajos,
    estamos dejando vivos zombies y las reglas son muy suaves.
    """
    mids = [e for e in exits if e.verdict == "continue"]
    if len(mids) < 3:
        return None

    avg_roas_mid = sum(e.roas for e in mids) / len(mids)
    avg_quality_mid = sum(e.quality_score for e in mids) / len(mids)

    if avg_roas_mid < 1.0 and avg_quality_mid < 0.6:
        return FeedbackSuggestion(
            code="exit.continue_rules.maybe_too_lenient",
            message=(
                "Varios productos en estado 'seguir probando' tienen ROAS y calidad bajos; "
                "considera endurecer las reglas de 'continue' en ExitCriteria."
            ),
            details={
                "continues": float(len(mids)),
                "avg_roas_continue": avg_roas_mid,
                "avg_quality_continue": avg_quality_mid,
            },
        )

    return None


# === API PRINCIPAL ===


def generate_feedback(path: Optional[Path] = None) -> List[FeedbackSuggestion]:
    """
    Lee product_exit desde Bitácora y genera sugerencias de ajuste de reglas.
    En F1 solo analizamos reglas de ExitCriteria (ROAS / continue).
    """
    if path is None:
        path = BITACORA_PATH

    exits = load_exits(path=path)
    if not exits:
        return []

    suggestions: List[FeedbackSuggestion] = []

    s1 = _suggest_roas_threshold(exits)
    if s1:
        suggestions.append(s1)

    s2 = _suggest_continue_rules(exits)
    if s2:
        suggestions.append(s2)

    return suggestions
