from decimal import Decimal

from vault.cashflow_v1 import CashFlowModel, CashFlowState


def test_cashflow_projected_available_cash_subtracts_cod_rejections():
    s = CashFlowState(
        available_cash=Decimal("100"),
        projected_refunds=Decimal("10"),
        projected_chargebacks=Decimal("5"),
        projected_cod_rejections=Decimal("20"),
    )

    assert s.projected_available_cash() == Decimal("65")
    assert s.net_available == Decimal("65")


def test_cashflow_can_spend_respects_cod_rejections_and_buffer():
    s = CashFlowState(
        available_cash=Decimal("100"),
        projected_cod_rejections=Decimal("25"),
        safety_buffer_cash=Decimal("10"),
    )

    assert s.can_spend(Decimal("65")) is True
    assert s.can_spend(Decimal("65.01")) is False


def test_cashflow_snapshot_preserves_cod_rejections():
    s = CashFlowState(
        available_cash=Decimal("50"),
        projected_cod_rejections=Decimal("7"),
    )

    snap = s.snapshot()

    assert snap is not s
    assert snap.projected_cod_rejections == Decimal("7")
    assert snap.available_cash == Decimal("50")


def test_cashflow_model_can_spend_respects_cod_rejections():
    model = CashFlowModel(
        state=CashFlowState(
            available_cash=Decimal("120"),
            projected_refunds=Decimal("10"),
            projected_chargebacks=Decimal("5"),
            projected_cod_rejections=Decimal("15"),
            safety_buffer_cash=Decimal("20"),
        )
    )

    assert model.can_spend(Decimal("70")) is True
    assert model.can_spend(Decimal("70.01")) is False
