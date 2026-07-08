# V3GAP:cashflow_timeline_per_payment_method

from decimal import Decimal

from vault.cashflow_v1 import CashFlowModel, CashFlowState, CashFlowTimelineEntry


def test_cashflow_timeline_lookup_by_payment_method():
    s = CashFlowState(
        payment_method_timeline=(
            CashFlowTimelineEntry(
                payment_method="card",
                available_cash=Decimal("100"),
                projected_refunds=Decimal("10"),
                settlement_days=2,
            ),
            CashFlowTimelineEntry(
                payment_method="cod",
                available_cash=Decimal("80"),
                projected_cod_rejections=Decimal("15"),
                settlement_days=5,
            ),
        )
    )

    cod = s.timeline_for("COD")
    assert cod.payment_method == "cod"
    assert cod.projected_available_cash == Decimal("65")
    assert cod.settlement_days == 5


def test_cashflow_timeline_lookup_returns_zero_entry_when_missing():
    s = CashFlowState()

    spei = s.timeline_for("spei")

    assert spei.payment_method == "spei"
    assert spei.projected_available_cash == Decimal("0")
    assert spei.settlement_days == 0


def test_cashflow_model_projected_available_cash_for_payment_method():
    model = CashFlowModel(
        state=CashFlowState(
            payment_method_timeline=(
                CashFlowTimelineEntry(
                    payment_method="card",
                    available_cash=Decimal("50"),
                    projected_refunds=Decimal("5"),
                ),
                CashFlowTimelineEntry(
                    payment_method="cod",
                    available_cash=Decimal("120"),
                    projected_cod_rejections=Decimal("20"),
                    projected_chargebacks=Decimal("10"),
                ),
            )
        )
    )

    assert model.projected_available_cash_for("card") == Decimal("45")
    assert model.projected_available_cash_for("cod") == Decimal("90")


def test_cashflow_snapshot_preserves_payment_method_timeline():
    s = CashFlowState(
        available_cash=Decimal("200"),
        payment_method_timeline=(
            CashFlowTimelineEntry(
                payment_method="card",
                available_cash=Decimal("120"),
                projected_refunds=Decimal("10"),
                settlement_days=1,
            ),
        ),
    )

    snap = s.snapshot()

    assert snap is not s
    assert len(snap.payment_method_timeline) == 1
    assert snap.payment_method_timeline[0].payment_method == "card"
    assert snap.payment_method_timeline[0].projected_available_cash == Decimal("110")
    assert snap.available_cash == Decimal("200")
