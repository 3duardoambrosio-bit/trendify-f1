# scripts/capital_demo.py

from ops.capital_shield_v2 import CapitalShieldV2 as CapitalShield
from infra.bitacora_auto import bitacora, EntryType


def run_capital_demo() -> None:
    """
    Demo simple de CapitalShield:
    - Mismo producto
    - Varios spends consecutivos
    - Vemos cuÃ¡ndo avisa (soft) y cuÃ¡ndo bloquea (hard)
    - Cada decisiÃ³n se registra en BitÃ¡cora
    """

    shield = CapitalShield()  # âš ï¸ Sin total_budget, usa la config del sistema

    product_id = "demo_product_1"
    spends = [10.0, 10.0, 15.0]  # Ajustado para forzar soft warning y hard block

    print("=== CAPITAL-SHIELD DEMO (spend por producto) ===\n")

    cumulative = 0.0

    for idx, amount in enumerate(spends, start=1):
        cumulative += amount

        decision = shield.register_spend(product_id, amount)

        print(f"[{idx}] Spend = {amount:.2f} | total_acumulado = {cumulative:.2f}")
        print(f"    allowed       : {decision.allowed}")
        print(f"    reason        : {decision.reason}")
        if getattr(decision, "soft_warnings", None):
            print(f"    soft_warnings : {decision.soft_warnings}")
        print()

        # Registramos la decisiÃ³n en BitÃ¡cora
        bitacora.log(
            entry_type=EntryType.PRODUCT_EVALUATION,  # por ahora usamos este tipo
            data={
                "source": "capital_demo",
                "product_id": product_id,
                "step": idx,
                "amount": amount,
                "cumulative_spend": cumulative,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "soft_warnings": getattr(decision, "soft_warnings", []),
            },
        )

    print("\n[SYNAPSE] Demo CapitalShield + BitÃ¡cora completada âœ…")


def main() -> None:
    run_capital_demo()


if __name__ == "__main__":
    main()

