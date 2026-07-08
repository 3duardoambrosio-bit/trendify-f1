from __future__ import annotations

from decimal import Decimal

from hypothesis import given, strategies as st

from ops.safety_middleware import (
    ODD_OUTSIDE,
    ODD_WITH_APPROVAL,
    ODD_WITHIN,
    build_layer0_descriptor,
    check_safety_before_spend,
    evaluate_odd,
    get_threshold_registry_v0,
    get_threshold_value,
    resolve_kill_switch_scope,
)
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


def test_on_trip_callback_called_when_blocked() -> None:
    limits = RiskLimits()
    snap = RiskSnapshot(
        monthly_budget=Decimal("100"),
        expected_spend_rate_4h=Decimal("10"),
        actual_spend_4h=Decimal("0"),
        daily_loss=Decimal("99"),
    )
    called = {"n": 0}

    def on_trip(decision):
        called["n"] += 1

    try:
        run_safety_gate(snapshot=snap, limits=limits, on_trip=on_trip)
    except SafetyGateTripped:
        pass

    assert called["n"] == 1


def test_gate_allows_safe_snapshot() -> None:
    limits = RiskLimits()
    snap = RiskSnapshot(
        monthly_budget=Decimal("300"),
        expected_spend_rate_4h=Decimal("10"),
        actual_spend_4h=Decimal("5"),
        daily_loss=Decimal("1"),
    )
    d = run_safety_gate(snapshot=snap, limits=limits)
    assert d.allowed is True


def test_threshold_registry_v0_contains_week1_contracts() -> None:
    registry = get_threshold_registry_v0()

    assert registry["spend_freshness_max_lag"].threshold_id == "TR-001"
    assert registry["tracking_freshness_max_lag"].threshold_id == "TR-002"
    assert registry["spend_envelope_daily_per_campaign"].threshold_id == "TR-006"
    assert registry["heartbeat_degraded_after"].threshold_id == "TR-011"
    assert registry["kill_switch_scope_default"].threshold_id == "TR-031"

    assert Decimal(str(get_threshold_value("spend_envelope_daily_per_campaign"))) == Decimal("1500")
    assert int(get_threshold_value("heartbeat_minimal_risk_after")) == 120
    assert str(get_threshold_value("kill_switch_scope_default")) == "per_channel"


def test_evaluate_odd_worst_state_wins() -> None:
    odd = evaluate_odd(
        channel="meta",
        country="MX",
        currency="MXN",
        spend_mxn=Decimal("2000"),
        data_freshness_minutes=10,
        tracking_freshness_minutes=10,
        heartbeat_age_minutes=10,
    )

    assert odd.state == ODD_OUTSIDE
    assert odd.minimal_risk_mode is True
    assert "SPEND_ABOVE_DAILY_CAMPAIGN_ENVELOPE" in odd.reason_codes


def test_evaluate_odd_degraded_heartbeat_requires_approval() -> None:
    odd = evaluate_odd(
        channel="meta",
        country="MX",
        currency="MXN",
        spend_mxn=Decimal("200"),
        data_freshness_minutes=10,
        tracking_freshness_minutes=10,
        heartbeat_age_minutes=90,
    )

    assert odd.state == ODD_WITH_APPROVAL
    assert odd.requires_human_approval is True
    assert "HEARTBEAT_DEGRADED_APPROVAL_REQUIRED" in odd.reason_codes


def test_evaluate_odd_clean_case_is_within_odd() -> None:
    odd = evaluate_odd(
        channel="meta",
        country="MX",
        currency="MXN",
        spend_mxn=Decimal("200"),
        data_freshness_minutes=10,
        tracking_freshness_minutes=10,
        heartbeat_age_minutes=10,
    )

    assert odd.state == ODD_WITHIN
    assert odd.requires_human_approval is False
    assert odd.minimal_risk_mode is False


def test_resolve_kill_switch_scope_default_per_channel() -> None:
    resolved = resolve_kill_switch_scope(channel="meta")
    assert resolved == {"scope": "per_channel", "target_id": "meta"}


def test_build_layer0_descriptor_exposes_scope_and_threshold_refs() -> None:
    descriptor = build_layer0_descriptor(
        component="spend_gateway_v1",
        channel="meta",
        threshold_keys=(
            "spend_envelope_daily_per_campaign",
            "heartbeat_degraded_after",
            "kill_switch_scope_default",
        ),
    )

    assert descriptor["layer"] == "L0"
    assert descriptor["component"] == "spend_gateway_v1"
    assert descriptor["kill_switch_scope"] == "per_channel"
    assert descriptor["kill_switch_target"] == "meta"
    assert descriptor["global_authority"] == "human_only"
    assert descriptor["threshold_refs"] == ["TR-006", "TR-011", "TR-031"]

def test_check_safety_before_spend_preserves_legacy_default_without_enforce_odd() -> None:
    result = check_safety_before_spend(
        amount=Decimal("2000"),
        operation_id="op-outside-legacy",
        channel="meta",
        country="MX",
        currency="MXN",
        data_freshness_minutes=0,
        tracking_freshness_minutes=0,
        heartbeat_age_minutes=0,
    )

    assert result.is_err() is False


def test_check_safety_before_spend_enforces_odd_when_explicitly_requested() -> None:
    result = check_safety_before_spend(
        amount=Decimal("2000"),
        operation_id="op-outside-enforced",
        enforce_odd=True,
        channel="meta",
        country="MX",
        currency="MXN",
        data_freshness_minutes=0,
        tracking_freshness_minutes=0,
        heartbeat_age_minutes=0,
    )

    assert result.is_err() is True
    assert str(result.error).startswith("ODD_OUTSIDE:")


def test_check_safety_before_spend_allows_within_odd_when_explicitly_requested() -> None:
    result = check_safety_before_spend(
        amount=Decimal("200"),
        operation_id="op-within-enforced",
        enforce_odd=True,
        channel="meta",
        country="MX",
        currency="MXN",
        data_freshness_minutes=0,
        tracking_freshness_minutes=0,
        heartbeat_age_minutes=0,
    )

    assert result.is_err() is False
