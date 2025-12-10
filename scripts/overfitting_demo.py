from __future__ import annotations

from ops.systems.overfitting_guard import analyze_overfitting


def main() -> None:
    alerts = analyze_overfitting()

    print("=== OVERFITTING-GUARD DEMO ===\n")

    if not alerts:
        print("[OVERFITTING] Sin alertas graves ✅")
    else:
        print(f"[OVERFITTING] {len(alerts)} alerta(s) detectadas:\n")
        for idx, alert in enumerate(alerts, start=1):
            print(f"- [{idx}] {alert.type}")
            print(f"    desc : {alert.description}")
            print(f"    sug. : {alert.recommendation}\n")

    print("\n[SYNAPSE] Demo Overfitting-Guard completada ✅")


if __name__ == "__main__":
    main()
