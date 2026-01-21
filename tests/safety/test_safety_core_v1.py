from synapse.safety.limits import RiskLimits, RiskSnapshot, evaluate_risk
from synapse.safety.killswitch import KillSwitch, KillSwitchLevel, KillSwitchActivation
from synapse.safety.circuit import CircuitBreaker, CircuitConfig, CircuitState
from synapse.safety.audit import AuditTrail


def test_risk_limits_daily_loss_blocks():
    limits = RiskLimits(daily_loss_limit=0.05)
    snap = RiskSnapshot(monthly_budget=1000, expected_spend_rate_4h=100, actual_spend_4h=100, daily_loss=60)
    dec = evaluate_risk(limits, snap)
    assert dec.allowed is False
    assert dec.reason == "DAILY_LOSS_LIMIT_EXCEEDED"


def test_risk_limits_spend_rate_blocks():
    limits = RiskLimits(spend_rate_anomaly_mult=3.0)
    snap = RiskSnapshot(monthly_budget=1000, expected_spend_rate_4h=100, actual_spend_4h=350, daily_loss=0)
    dec = evaluate_risk(limits, snap)
    assert dec.allowed is False
    assert dec.reason == "SPEND_RATE_ANOMALY"


def test_kill_switch_activation_and_clear():
    ks = KillSwitch()
    assert ks.is_active(KillSwitchLevel.PORTFOLIO) is False
    ks.activate(KillSwitchActivation(level=KillSwitchLevel.PORTFOLIO, reason="TEST"))
    assert ks.is_active(KillSwitchLevel.PORTFOLIO) is True
    ks.clear(KillSwitchLevel.PORTFOLIO)
    assert ks.is_active(KillSwitchLevel.PORTFOLIO) is False


def test_circuit_breaker_opens_and_cools_down():
    cb = CircuitBreaker(CircuitConfig(failure_threshold=2, success_threshold=1, cooldown_seconds=0))
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_audit_trail_hash_chain_verifies(tmp_path):
    path = tmp_path / "events.ndjson"
    a = AuditTrail(str(path))
    a.append("EVT1", {"x": 1}, actor="system", correlation_id="c1")
    a.append("EVT2", {"y": 2}, actor="system", correlation_id="c1")
    assert a.verify() is True
