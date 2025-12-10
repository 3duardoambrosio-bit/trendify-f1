from pathlib import Path

from infra.bitacora_auto import BitacoraAuto, EntryType
from ops.systems.feedback_engine import generate_feedback


def _log_exit(
    bitacora: BitacoraAuto,
    product_id: str,
    verdict: str,
    roas: float,
    quality_score: float,
    reason: str = "test_reason",
) -> None:
    bitacora.log(
        entry_type=EntryType.PRODUCT_EXIT,
        data={
            "product_id": product_id,
            "verdict": verdict,
            "reason": reason,
            "roas": roas,
            "quality_score": quality_score,
        },
    )


def test_no_feedback_with_few_exits(tmp_path: Path) -> None:
    """Con pocos eventos no debe sugerir nada."""
    path = tmp_path / "bitacora.jsonl"
    bitacora = BitacoraAuto(path=path)

    _log_exit(bitacora, "p1", "kill", 0.5, 0.5)

    suggestions = generate_feedback(path=path)
    assert suggestions == []


def test_suggests_roas_threshold_when_kills_good(tmp_path: Path) -> None:
    """Si matamos muchos productos con buen ROAS y calidad, sugiere relajar ROAS mínimo."""
    path = tmp_path / "bitacora.jsonl"
    bitacora = BitacoraAuto(path=path)

    for i in range(5):
        _log_exit(bitacora, f"k{i}", "kill", roas=1.1, quality_score=0.8)

    suggestions = generate_feedback(path=path)
    codes = {s.code for s in suggestions}

    assert "exit.roas_threshold.maybe_too_strict" in codes


def test_suggests_continue_rules_when_zombies(tmp_path: Path) -> None:
    """Si hay muchos 'continue' zombies, sugiere endurecer reglas de continue."""
    path = tmp_path / "bitacora.jsonl"
    bitacora = BitacoraAuto(path=path)

    for i in range(5):
        _log_exit(bitacora, f"c{i}", "continue", roas=0.7, quality_score=0.5)

    suggestions = generate_feedback(path=path)
    codes = {s.code for s in suggestions}

    assert "exit.continue_rules.maybe_too_lenient" in codes
