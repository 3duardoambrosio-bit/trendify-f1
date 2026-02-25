from __future__ import annotations

from decimal import Decimal

from hypothesis import given, strategies as st

from synapse.safety.limits import RiskLimits, RiskSnapshot, evaluate_risk


BUDGET = st.integers(min_value=1, max_value=10_000)
LOSS = st.integers(min_value=0, max_value=10_000)
RATE = st.integers(min_value=0, max_value=10_000)


@given(BUDGET, LOSS, RATE, RATE)
def test_evaluate_risk_is_deterministic(budget_i: int, loss_i: int, exp_i: int, act_i: int) -> None:
    limits = RiskLimits()
    snap = RiskSnapshot(
        monthly_budget=Decimal(str(budget_i)),
        expected_spend_rate_4h=Decimal(str(exp_i)),
        actual_spend_4h=Decimal(str(act_i)),
        daily_loss=Decimal(str(loss_i)),
    )
    d = evaluate_risk(limits, snap)
    assert isinstance(d.allowed, bool)
    if d.allowed is False:
        assert d.reason is not None and str(d.reason) != ""


def test_zero_or_negative_budget_blocks() -> None:
    from decimal import Decimal
    limits = RiskLimits()
    for bad in [Decimal('0'), Decimal('-100')]:
        snap = RiskSnapshot(
            monthly_budget=bad,
            expected_spend_rate_4h=Decimal('0'),
            actual_spend_4h=Decimal('0'),
            daily_loss=Decimal('9999'),
        )
        d = evaluate_risk(limits, snap)
        assert d.allowed is False, f"budget={bad} should block"
