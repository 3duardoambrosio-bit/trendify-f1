from ops.systems.tribunal import load_exit_events, summarize_exits, find_suspicious_exits


def main() -> None:
    events = load_exit_events()

    if not events:
        print("[TRIBUNAL] No hay entradas product_exit en Bitácora todavía.")
        return

    summary = summarize_exits(events)

    print("=== TRIBUNAL: RESUMEN product_exit ===")
    print(f"Total exits    : {summary.total_exits}")
    print(f"Kills          : {summary.kills} ({summary.kill_rate:.0%})")
    print(f"Scales         : {summary.scales} ({summary.scale_rate:.0%})")
    print(f"Continue       : {summary.continues} ({summary.continue_rate:.0%})")
    print()
    print(f"ROAS promedio  : {summary.avg_roas:.2f}")
    print(f"Quality prom   : {summary.avg_quality:.2f}")
    print(f"Días promedio  : {summary.avg_days_running:.1f}")
    print()

    anomalies = find_suspicious_exits(events)

    if not anomalies:
        print("[TRIBUNAL] Sin decisiones dudosas detectadas ✅")
    else:
        print("[TRIBUNAL] Posibles decisiones para revisar:")
        for a in anomalies:
            print(
                f"- {a.product_id} | verdict={a.verdict} | roas={a.roas:.2f} | "
                f"quality={a.quality_score:.2f} | tipo={a.anomaly_type}"
            )


if __name__ == "__main__":
    main()
