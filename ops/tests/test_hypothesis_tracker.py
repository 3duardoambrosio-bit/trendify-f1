from pathlib import Path

from infra.bitacora_auto import BitacoraAuto, EntryType
from ops.systems.hypothesis_tracker import HypothesisTracker, HypothesisStatus


def test_register_and_close_hypothesis(tmp_path):
    path: Path = tmp_path / "bitacora.jsonl"
    bitacora = BitacoraAuto(path=path)
    tracker = HypothesisTracker(bitacora=bitacora)

    hyp = tracker.register(
        area="buyer",
        statement="Subir margen mínimo a 0.35 mejora ROAS",
        metric="roas",
        baseline_value=1.2,
    )

    # Se genera un ID razonable y queda en pending
    assert hyp.id.startswith("HYP-")
    assert hyp.status == HypothesisStatus.PENDING

    # Debe existir al menos un evento de hipótesis en la bitácora
    entries = bitacora.load_entries()
    assert any(e.entry_type == EntryType.HYPOTHESIS_EVENT for e in entries)

    # Cerramos como VALIDATED
    tracker.close(
        hypothesis_id=hyp.id,
        result=HypothesisStatus.VALIDATED,
        new_value=1.6,
    )

    summary = tracker.summarize()
    assert summary["total"] == 1
    assert summary["validated"] == 1
    assert summary["invalidated"] == 0
    assert summary["pending"] == 0


def test_pending_when_no_close(tmp_path):
    path: Path = tmp_path / "bitacora.jsonl"
    bitacora = BitacoraAuto(path=path)
    tracker = HypothesisTracker(bitacora=bitacora)

    tracker.register(
        area="marketing",
        statement="Cambiar hook principal sube CTR",
        metric="ctr",
        baseline_value=1.0,
    )

    summary = tracker.summarize()
    assert summary["total"] == 1
    assert summary["validated"] == 0
    assert summary["invalidated"] == 0
    assert summary["pending"] == 1
