from decimal import Decimal

def test_cashflow_contract_for_spend_gateway_v2():
    from vault.cashflow_v1 import CashflowConfig, CashflowState, CashflowModel

    m = CashflowModel(
        CashflowConfig(safety_buffer=Decimal("20.00")),
        CashflowState(available_cash=Decimal("25.00"))
    )

    assert hasattr(m, "snapshot")
    assert hasattr(m, "debit_available")
    assert hasattr(m, "can_spend")

    # buffer: 25-20 => solo 5 spendable
    assert m.can_spend(Decimal("10.00")) is False
    assert m.can_spend(Decimal("5.00")) is True

    snap0 = m.snapshot()
    assert snap0.available_cash == Decimal("25.00")

    m.debit_available(Decimal("5.00"))
    snap1 = m.snapshot()
    assert snap1.available_cash == Decimal("20.00")