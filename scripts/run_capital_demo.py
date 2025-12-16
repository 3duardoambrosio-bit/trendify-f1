from __future__ import annotations

import sys
from pathlib import Path
from decimal import Decimal
from typing import Any, List

# --- Bootstrap de path para poder importar ops/* desde scripts/ ---

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Imports internos
from ops.catalog_pipeline import (
    load_catalog_csv,
    evaluate_catalog,
)
from ops.capital_shield_v2 import CapitalShieldV2, CapitalDecision


class FakeVault:
    """
    Vault de demo ultra simple.

    - Tiene un saldo inicial global.
    - Cada request_spend(amount, budget_type):
        - Si amount <= remaining → descuenta y regresa True.
        - Si no → regresa False.

    Solo es para mostrar cómo se comporta CapitalShieldV2 frente a un
    presupuesto limitado o suficiente, sin depender del Vault real.
    """

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


def _run_scenario(
    items: List[Any],
    vault_budget: Decimal,
    requested_per_product: Decimal,
    scenario_name: str,
) -> None:
    """
    Corre un escenario de asignación de capital:

    - Toma la lista de CatalogItemResult del catálogo.
    - Crea un FakeVault con cierto presupuesto.
    - Usa CapitalShieldV2 para decidir cuánto asignar a cada producto.
    """

    _print_header(f"SCENARIO: {scenario_name}")

    vault = FakeVault(vault_budget)
    shield = CapitalShieldV2(vault=vault, default_budget_type="learning")

    total_requested = Decimal("0")
    total_allocated = Decimal("0")
    approved_count = 0

    rows: list[tuple[str, str, Decimal, CapitalDecision]] = []

    for item in items:
        product_id = getattr(item, "product_id", "")
        final_decision = str(getattr(item, "final_decision", ""))

        if final_decision == "approved":
            approved_count += 1
            requested = requested_per_product
        else:
            requested = Decimal("0")

        total_requested += requested

        decision = shield.decide_for_product(
            final_decision=final_decision,
            requested_amount=requested,
        )

        total_allocated += decision.allocated

        rows.append(
            (
                product_id,
                final_decision,
                requested,
                decision,
            )
        )

    # Resumen numérico
    print(f"Budget inicial del vault      : {vault.initial_budget:.2f}")
    print(f"Productos aprobados           : {approved_count}")
    print(f"Budget solicitado total       : {total_requested:.2f}")
    print(f"Budget realmente asignado     : {total_allocated:.2f}")
    print(f"Budget restante en el vault   : {vault.remaining:.2f}")
    print(f"Llamadas a vault.request_spend: {len(vault.calls)}")

    # Tabla rápida por producto
    print("\nDetalle por producto (id, dec, requested, allocated, reason):")
    for product_id, final_decision, requested, decision in rows:
        print(
            f"- {product_id:>4} | dec={final_decision:9} "
            f"| req={requested:6.2f} "
            f"| alloc={decision.allocated:6.2f} "
            f"| reason={decision.reason}"
        )


def main() -> None:
    # 1) Cargar catálogo demo usando el pipeline actual
    data_path = (
        Path(__file__)
        .resolve()
        .parent.parent
        / "data"
        / "catalog"
        / "demo_catalog.csv"
    )

    catalog = load_catalog_csv(data_path)
    items, summary = evaluate_catalog(
        catalog,
        total_test_budget=100.0,
    )

    _print_header("RESUMEN DEL CATALOGO (BASE)")
    print(f"Total productos      : {summary.total_products}")
    print(f"Aprobados            : {summary.approved}")
    print(f"Rechazados           : {summary.rejected}")
    print(f"En revisión          : {summary.needs_review}")

    # 2) Escenario A: presupuesto suficiente (100 para 20 productos x 5)
    _run_scenario(
        items=items,
        vault_budget=Decimal("100"),
        requested_per_product=Decimal("5"),
        scenario_name="VAULT SUFICIENTE (100 para 20 x 5)",
    )

    # 3) Escenario B: presupuesto limitado (40 para 20 productos x 5)
    _run_scenario(
        items=items,
        vault_budget=Decimal("40"),
        requested_per_product=Decimal("5"),
        scenario_name="VAULT LIMITADO (40 para 20 x 5)",
    )


if __name__ == "__main__":
    main()
