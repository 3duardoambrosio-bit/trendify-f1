from __future__ import annotations

from decimal import Decimal

from hypothesis import given, strategies as st

from synapse.safety.limits import RiskLimits, RiskSnapshot
from synapse.safety.safe_execute import safe_execute


BUDGET = st.integers(min_value=1, max_value=10_000)
LOSS = st.integers(min_value=0, max_value=10_000)


@given(BUDGET, LOSS)
def test_safe_execute_runs_action_only_when_allowed(budget_i: int, loss_i: int) -> None:
    limits = RiskLimits()
    budget = Decimal(str(budget_i))
    loss = Decimal(str(loss_i))

    snap = RiskSnapshot(
        monthly_budget=budget,
        expected_spend_rate_4h=Decimal("0"),
        actual_spend_4h=Decimal("0"),
        daily_loss=loss,
    )

    called = {"n": 0}

    def action():
        called["n"] += 1
        return "OK"

    r = safe_execute(snapshot=snap, limits=limits, action=action)

    if r.executed:
        assert called["n"] == 1
        assert r.result == "OK"
        assert r.error is None
    else:
        assert called["n"] == 0
        assert r.result is None
        assert r.error is not None
