from pathlib import Path

from infra.bitacora_auto import BitacoraAuto
from ops.systems.overfitting_guard import analyze_overfitting


def _log_eval(bitacora: BitacoraAuto,
              product_id: str,
              composite_score: float,
              quality_score: float,
              final_decision: str = "approved") -> None:
    bitacora.log(
        entry_type="product_evaluation",
        data={
            "product_id": product_id,
            "buyer_scores": {"composite_score": composite_score},
            "quality_global_score": quality_score,
            "final_decision": final_decision,
        },
    )


def _log_exit(bitacora: BitacoraAuto,
              product_id: str,
              roas: float,
              quality_score: float,
              verdict: str) -> None:
    bitacora.log(
        entry_type="product_exit",
        data={
            "product_id": product_id,
            "days_running": 3,
            "total_spend": 30.0,
            "total_revenue": roas * 30.0,
            "roas": roas,
            "quality_score": quality_score,
            "verdict": verdict,
            "reason": "test",
        },
    )


def test_detects_low_variance_score(tmp_path):
    """Si todos los scores son casi iguales, debe levantar alerta."""
    path: Path = tmp_path / "bitacora.jsonl"
    bitacora = BitacoraAuto(path=path)

    # 5 productos con exactamente el mismo score
    for i in range(5):
        _log_eval(bitacora, f"prod_{i}", composite_score=0.8, quality_score=0.8)
        _log_exit(bitacora, f"prod_{i}", roas=1.0, quality_score=0.8, verdict="continue")

    alerts = analyze_overfitting(path=path)
    types = {a.type for a in alerts}
    assert "LOW_VARIANCE_SCORE" in types


def test_no_low_variance_when_scores_diverse(tmp_path):
    """Si los scores están bien distribuidos, no debe haber alerta de low variance."""
    path: Path = tmp_path / "bitacora.jsonl"
    bitacora = BitacoraAuto(path=path)

    scores = [0.2, 0.4, 0.6, 0.8, 0.9]
    for i, sc in enumerate(scores):
        verdict = "scale" if sc >= 0.8 else "kill"
        roas = 3.0 if sc >= 0.8 else 0.5

        _log_eval(bitacora, f"prod_{i}", composite_score=sc, quality_score=sc)
        _log_exit(bitacora, f"prod_{i}", roas=roas, quality_score=sc, verdict=verdict)

    alerts = analyze_overfitting(path=path)
    types = {a.type for a in alerts}
    assert "LOW_VARIANCE_SCORE" not in types
