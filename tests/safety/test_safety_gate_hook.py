import pytest

from synapse.safety.limits import RiskLimits, RiskSnapshot
from synapse.safety.gate import run_safety_gate, SafetyGateTripped


def test_safety_gate_allows_when_ok():
    limits = RiskLimits(
        daily_loss_limit=0.05,
        spend_rate_anomaly_mult=3.0,
        max_single_campaign_share=0.25,
    )
    snapshot = RiskSnapshot(
        monthly_budget=1000.0,
        expected_spend_rate_4h=100.0,
        actual_spend_4h=120.0,
        daily_loss=10.0,
    )

    d = run_safety_gate(snapshot=snapshot, limits=limits)
    assert d.allowed is True


def test_safety_gate_trips_when_violation():
    limits = RiskLimits(
        daily_loss_limit=0.05,
        spend_rate_anomaly_mult=3.0,
        max_single_campaign_share=0.25,
    )
    snapshot = RiskSnapshot(
        monthly_budget=1000.0,
        expected_spend_rate_4h=100.0,
        actual_spend_4h=120.0,
        daily_loss=80.0,
    )

    with pytest.raises(SafetyGateTripped):
        run_safety_gate(snapshot=snapshot, limits=limits)