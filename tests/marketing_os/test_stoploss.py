from __future__ import annotations

from synapse.marketing_os.experiment_stoploss import default_policy_mx, evaluate_stop_loss


def test_stoploss_trips_when_spend_high_roas_low() -> None:
    pol = default_policy_mx()
    r = evaluate_stop_loss(spend_mxn=pol.max_spend_mxn + 1, revenue_mxn=0.0, events=pol.min_events, policy=pol)
    assert r["breached_spend"] is True
    assert r["breached_roas"] is True
    assert r["should_stop"] is True


def test_stoploss_not_trip_without_events() -> None:
    pol = default_policy_mx()
    r = evaluate_stop_loss(spend_mxn=pol.max_spend_mxn + 1, revenue_mxn=0.0, events=0, policy=pol)
    assert r["should_stop"] is False
