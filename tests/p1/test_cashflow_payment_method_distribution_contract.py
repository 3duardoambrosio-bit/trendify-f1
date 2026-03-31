from decimal import Decimal

from vault.cashflow_v1 import (
    CashFlowDistributionEntry,
    CashFlowModel,
    CashFlowState,
    CashFlowTimelineEntry,
)


def test_cashflow_distribution_uses_projected_available_cash():
    s = CashFlowState(
        payment_method_timeline=(
            CashFlowTimelineEntry(
                payment_method="card",
                available_cash=Decimal("100"),
                projected_refunds=Decimal("10"),
            ),
            CashFlowTimelineEntry(
                payment_method="cod",
                available_cash=Decimal("80"),
                projected_cod_rejections=Decimal("20"),
            ),
        )
    )

    rows = s.payment_method_distribution()

    assert len(rows) == 2
    by_method = {r.payment_method: r for r in rows}
    assert by_method["card"].projected_available_cash == Decimal("90")
    assert by_method["cod"].projected_available_cash == Decimal("60")
    assert by_method["card"].share == Decimal("0.6")
    assert by_method["cod"].share == Decimal("0.4")


def test_cashflow_distribution_zero_total_keeps_zero_shares():
    s = CashFlowState(
        payment_method_timeline=(
            CashFlowTimelineEntry(
                payment_method="card",
                available_cash=Decimal("0"),
            ),
            CashFlowTimelineEntry(
                payment_method="cod",
                available_cash=Decimal("0"),
            ),
        )
    )

    rows = s.payment_method_distribution()

    assert len(rows) == 2
    assert all(r.share == Decimal("0") for r in rows)


def test_cashflow_model_distribution_matches_state():
    model = CashFlowModel(
        state=CashFlowState(
            payment_method_timeline=(
                CashFlowTimelineEntry(
                    payment_method="card",
                    available_cash=Decimal("45"),
                ),
                CashFlowTimelineEntry(
                    payment_method="spei",
                    available_cash=Decimal("55"),
                ),
            )
        )
    )

    rows = model.payment_method_distribution()

    assert len(rows) == 2
    assert isinstance(rows[0], CashFlowDistributionEntry)
    by_method = {r.payment_method: r for r in rows}
    assert by_method["card"].share == Decimal("0.45")
    assert by_method["spei"].share == Decimal("0.55")
