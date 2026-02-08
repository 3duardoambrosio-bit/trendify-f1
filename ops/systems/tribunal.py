from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


BITACORA_PATH = Path("data/bitacora/bitacora.jsonl")


@dataclass
class ExitEvent:
    """Evento de salida de producto (product_exit en Bitácora)."""

    product_id: str
    days_running: int
    total_spend: float
    total_revenue: float
    roas: float
    quality_score: float
    verdict: str  # "kill" | "scale" | "continue"
    reason: str
    timestamp: datetime


@dataclass
class ExitAuditSummary:
    """Resumen de cómo estamos tomando decisiones de salida."""

    total_exits: int

    kills: int
    scales: int
    continues: int

    avg_roas: float
    avg_quality: float
    avg_days_running: float

    kill_rate: float
    scale_rate: float
    continue_rate: float


def _safe_div(num: float, denom: int) -> float:
    return num / denom if denom else 0.0


def load_exit_events(path: Path = BITACORA_PATH) -> List[ExitEvent]:
    """Lee product_exit de la Bitácora (JSONL) y los parsea a ExitEvent."""
    events: List[ExitEvent] = []

    if not path.exists():
        return events

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                # Línea corrupta, la brincamos
                continue

            if raw.get("entry_type") != "product_exit":
                continue

            data = raw.get("data", {})
            ts = raw.get("timestamp")

            try:
                timestamp = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
            except Exception:
                timestamp = datetime.now(timezone.utc)

            events.append(
                ExitEvent(
                    product_id=str(data.get("product_id", "")),
                    days_running=int(data.get("days_running", 0)),
                    total_spend=float(data.get("total_spend", 0.0)),
                    total_revenue=float(data.get("total_revenue", 0.0)),
                    roas=float(data.get("roas", 0.0)),
                    quality_score=float(data.get("quality_score", 0.0)),
                    verdict=str(data.get("verdict", "")),
                    reason=str(data.get("reason", "")),
                    timestamp=timestamp,
                )
            )

    return events


def summarize_exits(events: Iterable[ExitEvent]) -> ExitAuditSummary:
    """Hace resumen global de los product_exit."""
    events = list(events)
    n = len(events)

    kills = sum(1 for e in events if e.verdict == "kill")
    scales = sum(1 for e in events if e.verdict == "scale")
    continues = sum(1 for e in events if e.verdict == "continue")

    total_roas = sum(e.roas for e in events)
    total_quality = sum(e.quality_score for e in events)
    total_days = sum(e.days_running for e in events)

    return ExitAuditSummary(
        total_exits=n,
        kills=kills,
        scales=scales,
        continues=continues,
        avg_roas=_safe_div(total_roas, n),
        avg_quality=_safe_div(total_quality, n),
        avg_days_running=_safe_div(total_days, n),
        kill_rate=_safe_div(kills, n),
        scale_rate=_safe_div(scales, n),
        continue_rate=_safe_div(continues, n),
    )


@dataclass
class ExitAnomaly:
    """Decisiones que huelen raro: probablemente mal kill / mal scale."""

    product_id: str
    verdict: str
    roas: float
    quality_score: float
    reason: str
    anomaly_type: str  # "should_kill" | "should_scale"


def find_suspicious_exits(
    events: Iterable[ExitEvent],
    min_days_for_kill: int = 3,
    roas_kill_threshold: float = 0.8,
    roas_scale_threshold: float = 2.0,
    min_quality_for_scale: float = 0.8,
) -> List[ExitAnomaly]:
    """
    Reglas simples:

    - should_kill: muchos días corriendo, ROAS bajo y NO está en kill
    - should_scale: ROAS alto + calidad alta y NO está en scale
    """
    anomalies: List[ExitAnomaly] = []
    for e in events:
        # Debería estar muerto y sigue vivo
        if (
            e.days_running >= min_days_for_kill
            and e.roas < roas_kill_threshold
            and e.verdict != "kill"
        ):
            anomalies.append(
                ExitAnomaly(
                    product_id=e.product_id,
                    verdict=e.verdict,
                    roas=e.roas,
                    quality_score=e.quality_score,
                    reason=e.reason,
                    anomaly_type="should_kill",
                )
            )

        # Debería estar escalando y no lo estamos escalando
        if (
            e.roas >= roas_scale_threshold
            and e.quality_score >= min_quality_for_scale
            and e.verdict != "scale"
        ):
            anomalies.append(
                ExitAnomaly(
                    product_id=e.product_id,
                    verdict=e.verdict,
                    roas=e.roas,
                    quality_score=e.quality_score,
                    reason=e.reason,
                    anomaly_type="should_scale",
                )
            )

    return anomalies
