from __future__ import annotations

import sys
from pathlib import Path
from decimal import Decimal
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ops.autopilot_v2 import AutopilotV2, AutopilotContext, AutopilotDecision


class FakeVault:
    def __init__(self, initial_budget: Decimal) -> None:
        self.initial_budget = Decimal(initial_budget)
        self.remaining = Decimal(initial_budget)
        self.calls: list[tuple[Decimal, str]] = []

    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        amount = Decimal(amount)
        self.calls.append((amount, budget_type))
        if amount <= self.remaining:
            self.remaining -= amount
            return True
        return False


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _build_scenarios() -> List[Dict[str, Any]]:
    return [
        {
            "product_id": "p-new",
            "label": "Nuevo test con poco spend y ROAS decente",
            "final_decision": "approved",
            "roas": 0.9,
            "spend": Decimal("0"),
            "requested": Decimal("10"),
        },
        {
            "product_id": "p-bad",
            "label": "Producto que está quemando lana (ROAS muy bajo)",
            "final_decision": "approved",
            "roas": 0.3,
            "spend": Decimal("40"),
            "requested": Decimal("15"),
        },
        {
            "product_id": "p-gray",
            "label": "Producto en zona gris, ROAS borderline",
            "final_decision": "approved",
            "roas": 0.85,
            "spend": Decimal("30"),
            "requested": Decimal("15"),
        },
        {
            "product_id": "p-winner",
            "label": "Winner claro, buen ROAS y buen spend",
            "final_decision": "approved",
            "roas": 1.8,
            "spend": Decimal("50"),
            "requested": Decimal("20"),
        },
        {
            "product_id": "p-no-budget",
            "label": "Tiene buenos números pero el vault está seco",
            "final_decision": "approved",
            "roas": 1.3,
            "spend": Decimal("25"),
            "requested": Decimal("50"),
        },
        {
            "product_id": "p-rejected",
            "label": "Producto que el buyer ya rechazó",
            "final_decision": "rejected",
            "roas": 2.0,
            "spend": Decimal("60"),
            "requested": Decimal("20"),
        },
    ]


def main() -> None:
    _print_header("AUTOPILOT V2 DEMO")

    # Vault con 60 de presupuesto total para el demo
    vault = FakeVault(Decimal("60"))
    autopilot = AutopilotV2(vault=vault)

    scenarios = _build_scenarios()

    for scen in scenarios:
        ctx = AutopilotContext(
            product_id=scen["product_id"],
            final_decision=scen["final_decision"],
            current_roas=scen["roas"],
            spend=scen["spend"],
            requested_budget=scen["requested"],
        )

        decision: AutopilotDecision = autopilot.decide(ctx)

        print(f"- [{ctx.product_id}] {scen['label']}")
        print(
            f"    roas={ctx.current_roas:.2f} | spend={ctx.spend:.2f} "
            f"| requested={ctx.requested_budget:.2f}"
        )
        print(
            f"    -> action={decision.action.upper()} "
            f"| allocated={decision.allocated_budget:.2f} "
            f"| reason={decision.reason}"
        )

    _print_header("ESTADO FINAL DEL VAULT (DEMO)")
    print(f"Budget inicial : {vault.initial_budget:.2f}")
    print(f"Budget restante: {vault.remaining:.2f}")
    print(f"Llamadas a Vault.request_spend: {len(vault.calls)}")


if __name__ == "__main__":
    main()
