from infra.bitacora_auto import BitacoraAuto
from ops.systems.hypothesis_tracker import HypothesisTracker, HypothesisStatus


def main() -> None:
    bitacora = BitacoraAuto()
    tracker = HypothesisTracker(bitacora=bitacora)

    h1 = tracker.register(
        area="buyer",
        statement="Subir margen mínimo a 0.35 mejora ROAS",
        metric="roas",
        baseline_value=1.4,
    )
    tracker.close(h1.id, HypothesisStatus.VALIDATED, new_value=1.8)

    h2 = tracker.register(
        area="marketing",
        statement="Nuevo hook en creativos mejora CTR",
        metric="ctr",
        baseline_value=1.0,
    )
    tracker.close(h2.id, HypothesisStatus.INVALIDATED, new_value=0.7)

    summary = tracker.summarize()

    print("=== HYPOTHESIS-TRACKER DEMO ===\n")
    print(f"Total hipótesis : {summary['total']}")
    print(f"Validadas       : {summary['validated']}")
    print(f"Invalidadas     : {summary['invalidated']}")
    print(f"Pendientes      : {summary['pending']}")
    print("\n[SYNAPSE] Demo Hypothesis-Tracker completada ✅")


if __name__ == "__main__":
    main()
