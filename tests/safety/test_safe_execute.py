from synapse.safety.limits import RiskLimits, RiskSnapshot
from synapse.safety.safe_execute import safe_execute


def test_safe_execute_blocks_action_when_gate_trips():
    limits = RiskLimits(daily_loss_limit=0.05, spend_rate_anomaly_mult=3.0, max_single_campaign_share=0.25)
    snap = RiskSnapshot(monthly_budget=1000.0, expected_spend_rate_4h=100.0, actual_spend_4h=120.0, daily_loss=80.0)

    ran = {"x": False}
    def action():
        ran["x"] = True
        return 123

    res = safe_execute(snapshot=snap, limits=limits, action=action)
    assert res.executed is False
    assert ran["x"] is False


def test_safe_execute_runs_action_when_ok():
    limits = RiskLimits(daily_loss_limit=0.05, spend_rate_anomaly_mult=3.0, max_single_campaign_share=0.25)
    snap = RiskSnapshot(monthly_budget=1000.0, expected_spend_rate_4h=100.0, actual_spend_4h=120.0, daily_loss=10.0)

    def action():
        return 456

    res = safe_execute(snapshot=snap, limits=limits, action=action)
    assert res.executed is True
    assert res.result == 456