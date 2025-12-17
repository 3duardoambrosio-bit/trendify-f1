from decimal import Decimal

def test_cashflow_state_has_legacy_methods():
    from vault.cashflow_v1 import CashFlowState
    s = CashFlowState(available_cash=Decimal("10"), safety_buffer_cash=Decimal("1"))
    assert hasattr(s, "can_spend")
    assert s.can_spend(Decimal("9")) is True
    assert s.can_spend(Decimal("10")) is False