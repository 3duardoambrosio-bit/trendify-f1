from __future__ import annotations

from synapse.marketing_os.quality_scoring import score_creatives


def test_score_creatives_returns_metrics_and_score() -> None:
    creatives = [
        {"primary_text": "Producto X que sí cumple: mejor valor."},
        {"primary_text": "Upgrade inmediato: Producto X. mejor valor."},
        {"primary_text": "Tu día a día, pero en modo PRO: Producto X."},
    ]
    q = score_creatives(creatives, title="Producto X")
    assert 0 <= q.score <= 100
    assert q.metrics["count"] == 3
    assert q.metrics["unique_ratio"] > 0.5


def test_score_penalizes_ultra_short() -> None:
    creatives = [{"primary_text": "ok"} for _ in range(5)]
    q = score_creatives(creatives, title="Producto X")
    assert q.score < 60
