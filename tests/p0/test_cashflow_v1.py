from decimal import Decimal
from vault.cashflow_v1 import CashflowV1, Hold


def test_projected_available_includes_releases_minus_refunds() -> None:
    cf = CashflowV1(
        available_cash=Decimal("20"),
        holds=[Hold(amount=Decimal("50"), release_in_days=7)],
        projected_refunds=Decimal("5"),
        safety_buffer=Decimal("10"),
    )
    assert cf.projected_available_in(0) == Decimal("15")
    assert cf.projected_available_in(7) == Decimal("65")


def test_runway_respects_safety_buffer() -> None:
    cf = CashflowV1(
        available_cash=Decimal("20"),
        holds=[],
        projected_refunds=Decimal("0"),
        safety_buffer=Decimal("10"),
    )
    # cash usable = 10; burn=2 => 5 días
    assert cf.runway_days(Decimal("2")) == 5


def test_can_spend_today_hard_stop() -> None:
    cf = CashflowV1(
        available_cash=Decimal("12"),
        holds=[],
        projected_refunds=Decimal("0"),
        safety_buffer=Decimal("10"),
    )
    assert cf.can_spend_today(Decimal("1")) is True
    assert cf.can_spend_today(Decimal("3")) is False