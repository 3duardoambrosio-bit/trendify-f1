# V3GAP:A-05_msi_fee_adjustment

from decimal import Decimal

from vault.cashflow_v1 import CashFlowModel, CashFlowState, CashFlowTimelineEntry


def test_cashflow_projected_available_cash_subtracts_msi_fees():
    s = CashFlowState(
        available_cash=Decimal("100"),
        projected_refunds=Decimal("10"),
        projected_chargebacks=Decimal("5"),
        projected_msi_fees=Decimal("20"),
    )

    assert s.projected_available_cash() == Decimal("65")
    assert s.net_available == Decimal("65")


def test_cashflow_timeline_entry_projected_available_cash_subtracts_msi_fees():
    entry = CashFlowTimelineEntry(
        payment_method="msi_6",
        available_cash=Decimal("120"),
        projected_refunds=Decimal("5"),
        projected_msi_fees=Decimal("15"),
        settlement_days=7,
    )

    assert entry.payment_method == "msi_6"
    assert entry.projected_available_cash == Decimal("100")
    assert entry.settlement_days == 7


def test_cashflow_distribution_respects_msi_fee_adjustment():
    s = CashFlowState(
        payment_method_timeline=(
            CashFlowTimelineEntry(
                payment_method="msi_6",
                available_cash=Decimal("100"),
                projected_msi_fees=Decimal("10"),
            ),
            CashFlowTimelineEntry(
                payment_method="card",
                available_cash=Decimal("60"),
            ),
        )
    )

    rows = s.payment_method_distribution()

    assert len(rows) == 2
    by_method = {r.payment_method: r for r in rows}
    assert by_method["msi_6"].projected_available_cash == Decimal("90")
    assert by_method["card"].projected_available_cash == Decimal("60")
    assert by_method["msi_6"].share == Decimal("0.6")
    assert by_method["card"].share == Decimal("0.4")


def test_cashflow_model_projected_available_cash_for_msi_method():
    model = CashFlowModel(
        state=CashFlowState(
            payment_method_timeline=(
                CashFlowTimelineEntry(
                    payment_method="msi_6",
                    available_cash=Decimal("70"),
                    projected_refunds=Decimal("5"),
                    projected_msi_fees=Decimal("10"),
                ),
            )
        )
    )

    assert model.projected_available_cash_for("MSI_6") == Decimal("55")


def test_cashflow_snapshot_preserves_msi_fees():
    s = CashFlowState(
        available_cash=Decimal("200"),
        projected_msi_fees=Decimal("9"),
        payment_method_timeline=(
            CashFlowTimelineEntry(
                payment_method="msi_6",
                available_cash=Decimal("120"),
                projected_msi_fees=Decimal("4"),
                settlement_days=3,
            ),
        ),
    )

    snap = s.snapshot()

    assert snap is not s
    assert snap.projected_msi_fees == Decimal("9")
    assert len(snap.payment_method_timeline) == 1
    assert snap.payment_method_timeline[0].payment_method == "msi_6"
    assert snap.payment_method_timeline[0].projected_msi_fees == Decimal("4")
    assert snap.payment_method_timeline[0].projected_available_cash == Decimal("116")