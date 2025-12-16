from __future__ import annotations

from decimal import Decimal
import random

import pytest

from infra.vault import Vault


# Si no tienes hypothesis instalado, estos tests se marcan como SKIPPED.
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st  # type: ignore[assignment]


decimals_money = st.decimals(
    min_value=Decimal("1.00"),
    max_value=Decimal("1000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)


@given(
    total=decimals_money,
    spends=st.lists(decimals_money, max_size=30),
)
def test_vault_never_exceeds_total_budget(total: Decimal, spends: list[Decimal]) -> None:
    vault = Vault.from_total(total)

    for amount in spends:
        bucket = "learning" if random.random() < 0.5 else "operational"
        _ = vault.request_spend(amount, bucket=bucket)
        # No nos importa si es Err o Ok; sólo que no viole invariantes

    assert vault.total_spent <= vault.total_budget
    # reserve NUNCA se toca
    snapshot = vault.snapshot()
    assert snapshot.reserve_budget == vault.reserve_budget


@given(total=decimals_money)
def test_vault_ratios_sum_correct(total: Decimal) -> None:
    vault = Vault.from_total(total)
    snapshot = vault.snapshot()

    # Sumatoria de bolsillos = total
    total_reconstructed = (
        snapshot.learning_budget + snapshot.operational_budget + snapshot.reserve_budget
    )
    assert total_reconstructed == snapshot.total_budget


@given(
    total=decimals_money,
    amount=decimals_money,
)
def test_cannot_spend_more_than_bucket(total: Decimal, amount: Decimal) -> None:
    vault = Vault.from_total(total)

    # Forzamos a gastar sólo en learning
    _ = vault.request_spend(vault.learning_budget, bucket="learning")
    # Este gasto extra en learning debería fallar
    res = vault.request_spend(amount, bucket="learning")
    if amount > 0:
        # Si amount es positivo, ya no debería caber nada en learning
        assert res.is_err()
