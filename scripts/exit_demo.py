from __future__ import annotations

from infra.bitacora_auto import BitacoraAuto, EntryType
from ops.exit_criteria import (
    ProductPerformanceSnapshot,
    evaluate_product_exit,
)


def print_decision(tag: str, snap: ProductPerformanceSnapshot, verdict, reason: str) -> None:
    print(f"\n=== {tag} ===")
    print(f"product_id    : {snap.product_id}")
    print(f"days_running  : {snap.days_running}")
    print(f"total_spend   : {snap.total_spend:.2f}")
    print(f"total_revenue : {snap.total_revenue:.2f}")
    print(f"ROAS          : {snap.roas:.2f}")
    print(f"quality_score : {snap.quality_score:.2f}")
    print(f"verdict       : {verdict.value}")
    print(f"reason        : {reason}")


def main() -> None:
    bitacora = BitacoraAuto()

    # Caso 1: perdedor claro → KILL
    loser = ProductPerformanceSnapshot(
        product_id="prod_loser",
        days_running=4,
        total_spend=60.0,
        total_revenue=20.0,  # ROAS = 0.33
        quality_score=0.6,
    )
    loser_decision = evaluate_product_exit(loser)
    print_decision("LOSER (debe morir)", loser, loser_decision.verdict, loser_decision.reason)

    bitacora.log(
        entry_type=EntryType.PRODUCT_EXIT,
        data={
            "product_id": loser.product_id,
            "days_running": loser.days_running,
            "total_spend": loser.total_spend,
            "total_revenue": loser.total_revenue,
            "roas": loser.roas,
            "quality_score": loser.quality_score,
            "verdict": loser_decision.verdict.value,
            "reason": loser_decision.reason,
        },
    )

    # Caso 2: ganador claro → SCALE
    winner = ProductPerformanceSnapshot(
        product_id="prod_winner",
        days_running=5,
        total_spend=50.0,
        total_revenue=180.0,  # ROAS = 3.6
        quality_score=0.9,
    )
    winner_decision = evaluate_product_exit(winner)
    print_decision("WINNER (debe escalar)", winner, winner_decision.verdict, winner_decision.reason)

    bitacora.log(
        entry_type=EntryType.PRODUCT_EXIT,
        data={
            "product_id": winner.product_id,
            "days_running": winner.days_running,
            "total_spend": winner.total_spend,
            "total_revenue": winner.total_revenue,
            "roas": winner.roas,
            "quality_score": winner.quality_score,
            "verdict": winner_decision.verdict.value,
            "reason": winner_decision.reason,
        },
    )

    # Caso 3: zona gris → CONTINUE
    mid = ProductPerformanceSnapshot(
        product_id="prod_mid",
        days_running=3,
        total_spend=30.0,
        total_revenue=45.0,  # ROAS = 1.5
        quality_score=0.75,
    )
    mid_decision = evaluate_product_exit(mid)
    print_decision("MID (seguir probando)", mid, mid_decision.verdict, mid_decision.reason)

    bitacora.log(
        entry_type=EntryType.PRODUCT_EXIT,
        data={
            "product_id": mid.product_id,
            "days_running": mid.days_running,
            "total_spend": mid.total_spend,
            "total_revenue": mid.total_revenue,
            "roas": mid.roas,
            "quality_score": mid.quality_score,
            "verdict": mid_decision.verdict.value,
            "reason": mid_decision.reason,
        },
    )

    print("\n[SYNAPSE] Demo ExitCriteria + Bitácora completada ✅")


if __name__ == "__main__":
    main()
