from decimal import Decimal
from vault.cashflow_v1 import CashFlowState


def test_cashflow_net_available_never_negative():
    s = CashFlowState(available_cash=Decimal("10"), projected_refunds=Decimal("20"))
    assert s.net_available == Decimal("0")


def test_cashflow_can_spend_respects_buffer():
    s = CashFlowState(available_cash=Decimal("100"), projected_refunds=Decimal("0"), projected_chargebacks=Decimal("0"), safety_buffer_cash=Decimal("30"))
    assert s.can_spend(Decimal("70")) is True
    assert s.can_spend(Decimal("70.01")) is False