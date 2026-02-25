from __future__ import annotations

from decimal import Decimal

from hypothesis import given, strategies as st

from synapse.safety.gate import SafetyGateTripped, run_safety_gate
from synapse.safety.limits import RiskLimits, RiskSnapshot


BUDGET = st.integers(min_value=1, max_value=10_000)
LOSS = st.integers(min_value=0, max_value=10_000)
RATE = st.integers(min_value=0, max_value=10_000)


@given(BUDGET, LOSS, RATE, RATE)
def test_run_safety_gate_matches_risk_rules(budget_i: int, loss_i: int, exp_i: int, act_i: int) -> None:
    budget = Decimal(str(budget_i))
    loss = Decimal(str(loss_i))
    exp = Decimal(str(exp_i))
    act = Decimal(str(act_i))

    limits = RiskLimits()
    snap = RiskSnapshot(monthly_budget=budget, expected_spend_rate_4h=exp, actual_spend_4h=act, daily_loss=loss)

    daily_cap = snap.monthly_budget * limits.daily_loss_limit
    auto_cap = snap.monthly_budget * limits.auto_killswitch_threshold

    should_block = False
    if snap.monthly_budget > 0 and snap.daily_loss >= auto_cap:
        should_block = True
    elif snap.monthly_budget > 0 and snap.daily_loss > daily_cap:
        should_block = True
    elif snap.expected_spend_rate_4h > 0 and snap.actual_spend_4h > (snap.expected_spend_rate_4h * limits.spend_rate_anomaly_mult):
        should_block = True

    if should_block:
        try:
            _ = run_safety_gate(snapshot=snap, limits=limits)
            assert False, "expected SafetyGateTripped"
        except SafetyGateTripped:
            assert True
    else:
        d = run_safety_gate(snapshot=snap, limits=limits)
        assert d.allowed is True
