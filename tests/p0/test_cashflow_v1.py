from decimal import Decimal
from vault.cashflow_v1 import CashflowState


def test_effective_available_deducts_risk():
    s = CashflowState(available_cash=Decimal("100"), projected_refunds=Decimal("10"), projected_chargebacks=Decimal("5"))
    assert s.effective_available == Decimal("85.00")


def test_can_spend_respects_buffer():
    s = CashflowState(available_cash=Decimal("100"), projected_refunds=Decimal("20"))
    assert s.can_spend(Decimal("50"), safety_buffer=Decimal("20")) is True   # 80-50 >=20
    assert s.can_spend(Decimal("61"), safety_buffer=Decimal("20")) is False  # 80-61 <20


def test_runway_days():
    s = CashflowState(available_cash=Decimal("90"))
    assert s.runway_days(Decimal("10")) >= 8