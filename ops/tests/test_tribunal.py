from infra.time_utils import now_utc

from datetime import datetime

import pytest

from ops.systems.tribunal import (
    ExitEvent,
    ExitAuditSummary,
    ExitAnomaly,
    load_exit_events,
    summarize_exits,
    find_suspicious_exits,
)


def _e(
    product_id: str,
    verdict: str,
    roas: float,
    quality: float,
    days: int = 3,
    reason: str = "test",
) -> ExitEvent:
    return ExitEvent(
        product_id=product_id,
        days_running=days,
        total_spend=10.0,
        total_revenue=roas * 10.0,
        roas=roas,
        quality_score=quality,
        verdict=verdict,
        reason=reason,
        timestamp=now_utc(),
    )


def test_summarize_exits_basic():
    events = [
        _e("loser", "kill", 0.5, 0.6, days=4),
        _e("winner", "scale", 3.0, 0.9, days=5),
        _e("mid", "continue", 1.5, 0.75, days=3),
    ]

    summary = summarize_exits(events)

    assert isinstance(summary, ExitAuditSummary)
    assert summary.total_exits == 3
    assert summary.kills == 1
    assert summary.scales == 1
    assert summary.continues == 1

    # promedios
    assert summary.avg_roas == pytest.approx((0.5 + 3.0 + 1.5) / 3)
    assert summary.avg_quality == pytest.approx((0.6 + 0.9 + 0.75) / 3)
    assert summary.avg_days_running == pytest.approx((4 + 5 + 3) / 3)

    # ratios
    assert summary.kill_rate == pytest.approx(1 / 3)
    assert summary.scale_rate == pytest.approx(1 / 3)
    assert summary.continue_rate == pytest.approx(1 / 3)


def test_find_suspicious_exits_flags_bad_calls():
    events = [
        # Mala decisión: debería estar en kill
        _e("bad_survivor", "continue", 0.4, 0.6, days=5),
        # Mala decisión: debería estar en scale
        _e("under_scaled", "continue", 3.2, 0.9, days=4),
        # Bien matado
        _e("proper_kill", "kill", 0.3, 0.5, days=4),
        # Bien escalado
        _e("proper_scale", "scale", 3.5, 0.9, days=5),
    ]

    anomalies = find_suspicious_exits(events)

    assert len(anomalies) == 2

    types = {a.anomaly_type for a in anomalies}
    ids = {a.product_id for a in anomalies}

    assert types == {"should_kill", "should_scale"}
    assert ids == {"bad_survivor", "under_scaled"}


def test_load_exit_events_filters_only_product_exit(tmp_path):
    path = tmp_path / "bitacora.jsonl"
    # 3 product_exit + 1 product_evaluation
    lines = [
        {
            "timestamp": "2025-12-05T10:00:00",
            "entry_type": "product_exit",
            "data": {
                "product_id": "p1",
                "days_running": 3,
                "total_spend": 30.0,
                "total_revenue": 60.0,
                "roas": 2.0,
                "quality_score": 0.8,
                "verdict": "scale",
                "reason": "winner",
            },
        },
        {
            "timestamp": "2025-12-05T10:05:00",
            "entry_type": "product_exit",
            "data": {
                "product_id": "p2",
                "days_running": 4,
                "total_spend": 40.0,
                "total_revenue": 20.0,
                "roas": 0.5,
                "quality_score": 0.6,
                "verdict": "kill",
                "reason": "loser",
            },
        },
        {
            "timestamp": "2025-12-05T10:10:00",
            "entry_type": "product_evaluation",
            "data": {"product_id": "p3"},
        },
        {
            "timestamp": "2025-12-05T10:15:00",
            "entry_type": "product_exit",
            "data": {
                "product_id": "p4",
                "days_running": 2,
                "total_spend": 20.0,
                "total_revenue": 30.0,
                "roas": 1.5,
                "quality_score": 0.7,
                "verdict": "continue",
                "reason": "mid",
            },
        },
    ]

    import json

    with path.open("w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")

    events = load_exit_events(path)

    assert len(events) == 3
    ids = {e.product_id for e in events}
    assert ids == {"p1", "p2", "p4"}
