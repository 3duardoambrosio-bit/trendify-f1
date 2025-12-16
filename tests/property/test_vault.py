from decimal import Decimal

from hypothesis import given, strategies as st

from core.result import Ok, Err
from vault.vault import Vault, SpendApproval, SpendError


# Estrategia para montos de gasto razonables
spend_amounts = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("50.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def test_vault_basic_invariants() -> None:
    vault = Vault(
        total_budget=Decimal("300"),
        learning_budget=Decimal("90"),
        operational_budget=Decimal("165"),
        reserve_budget=Decimal("45"),
    )

    assert vault.total_budget == Decimal("300")
    assert vault.learning_budget + vault.operational_budget + vault.reserve_budget == vault.total_budget
    assert vault.total_spent == Decimal("0")
    assert vault.reserve_intact is True


@given(spends=st.lists(spend_amounts, max_size=50))
def test_vault_never_exceeds_budget(spends: list[Decimal]) -> None:
    """
    Pase lo que pase con la secuencia de gastos, el Vault nunca
    permite que el dinero gastado exceda los budgets configurados.
    """
    vault = Vault(
        total_budget=Decimal("300"),
        learning_budget=Decimal("90"),
        operational_budget=Decimal("165"),
        reserve_budget=Decimal("45"),
    )

    for amount in spends:
        result = vault.request_spend(amount, "learning")

        if isinstance(result, Ok):
            # Cuando aprueba, el gasto se suma y se mantiene bajo el límite
            assert isinstance(result.value, SpendApproval)
            assert vault.learning_spent <= vault.learning_budget
        else:
            # Cuando falla, no se modifica el estado
            assert isinstance(result, Err)
            assert isinstance(result.error, SpendError)
            assert vault.learning_spent <= vault.learning_budget

        # Invariante global: nunca gastamos más del total
        assert vault.total_spent <= vault.total_budget


@given(spends=st.lists(spend_amounts, max_size=50))
def test_reserve_is_sacred(spends: list[Decimal]) -> None:
    """
    La reserve es sagrada: cualquier intento de gasto en 'reserve'
    debe fallar SIEMPRE y el Vault sigue reportando reserve_intact=True.
    """
    vault = Vault(
        total_budget=Decimal("300"),
        learning_budget=Decimal("90"),
        operational_budget=Decimal("165"),
        reserve_budget=Decimal("45"),
    )

    for amount in spends:
        result = vault.request_spend(amount, "reserve")
        assert isinstance(result, Err)
        assert isinstance(result.error, SpendError)
        assert result.error.budget_type == "reserve"
        assert vault.reserve_intact is True

    # Y no afecta a learning/operational
    assert vault.learning_spent == Decimal("0")
    assert vault.operational_spent == Decimal("0")
