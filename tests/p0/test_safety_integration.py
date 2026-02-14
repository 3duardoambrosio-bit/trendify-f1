from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from infra.result import Err, Ok
from ops.safety_middleware import check_safety_before_spend
from synapse.safety.killswitch import KillSwitch, KillSwitchActivation, KillSwitchLevel
from synapse.safety.limits import RiskLimits, RiskSnapshot


class _DummyCB:
    """Circuit breaker stub that always allows."""
    def __init__(self) -> None:
        self.state = SimpleNamespace(value="closed")

    def can_execute(self) -> bool:
        return True


# --- 1. Normal spend passes all safety checks ---


def test_normal_spend_passes(tmp_path) -> None:
    ks = KillSwitch(state_file=tmp_path / "ks.json")
    limits = RiskLimits()
    snap = RiskSnapshot(
        monthly_budget="1000.00",
        expected_spend_rate_4h="10.00",
        actual_spend_4h="5.00",
        daily_loss="10.00",   # 1% of budget — well below 80%
    )

    res = check_safety_before_spend(
        Decimal("5.00"),
        "op_normal",
        killswitch=ks,
        circuit_breaker=_DummyCB(),
        risk_snapshot=snap,
        risk_limits=limits,
    )
    assert isinstance(res, Ok)
    assert not ks.is_active(KillSwitchLevel.SYSTEM)


# --- 2. Spend that exceeds 80% activates killswitch ---


def test_spend_exceeding_80pct_activates_killswitch(tmp_path) -> None:
    ks = KillSwitch(state_file=tmp_path / "ks.json")
    limits = RiskLimits()  # auto_killswitch_threshold defaults to 0.80
    snap = RiskSnapshot(
        monthly_budget="1000.00",
        expected_spend_rate_4h="10.00",
        actual_spend_4h="5.00",
        daily_loss="800.00",  # exactly 80% of budget → triggers
    )

    res = check_safety_before_spend(
        Decimal("10.00"),
        "op_80pct",
        killswitch=ks,
        circuit_breaker=_DummyCB(),
        risk_snapshot=snap,
        risk_limits=limits,
        trip_system_killswitch_on_gate=True,
    )
    assert isinstance(res, Err)
    assert "AUTO_KILLSWITCH_THRESHOLD_EXCEEDED" in str(res.error)
    assert ks.is_active(KillSwitchLevel.SYSTEM)


def test_spend_above_80pct_activates_killswitch(tmp_path) -> None:
    ks = KillSwitch(state_file=tmp_path / "ks.json")
    limits = RiskLimits()
    snap = RiskSnapshot(
        monthly_budget="1000.00",
        expected_spend_rate_4h="10.00",
        actual_spend_4h="5.00",
        daily_loss="900.00",  # 90% — well above threshold
    )

    res = check_safety_before_spend(
        Decimal("10.00"),
        "op_90pct",
        killswitch=ks,
        circuit_breaker=_DummyCB(),
        risk_snapshot=snap,
        risk_limits=limits,
        trip_system_killswitch_on_gate=True,
    )
    assert isinstance(res, Err)
    assert ks.is_active(KillSwitchLevel.SYSTEM)


# --- 3. Active killswitch blocks all subsequent spend ---


def test_killswitch_active_blocks_all_spend(tmp_path) -> None:
    ks = KillSwitch(state_file=tmp_path / "ks.json")

    # First: trigger the killswitch via 80% threshold
    limits = RiskLimits()
    snap_trigger = RiskSnapshot(
        monthly_budget="1000.00",
        expected_spend_rate_4h="10.00",
        actual_spend_4h="5.00",
        daily_loss="850.00",
    )
    res1 = check_safety_before_spend(
        Decimal("10.00"),
        "op_trigger",
        killswitch=ks,
        risk_snapshot=snap_trigger,
        risk_limits=limits,
        trip_system_killswitch_on_gate=True,
    )
    assert isinstance(res1, Err)
    assert ks.is_active(KillSwitchLevel.SYSTEM)

    # Second: even a tiny, perfectly safe spend is now blocked by killswitch
    snap_safe = RiskSnapshot(
        monthly_budget="1000.00",
        expected_spend_rate_4h="10.00",
        actual_spend_4h="1.00",
        daily_loss="1.00",
    )
    res2 = check_safety_before_spend(
        Decimal("0.01"),
        "op_blocked",
        killswitch=ks,
        risk_snapshot=snap_safe,
        risk_limits=limits,
    )
    assert isinstance(res2, Err)
    assert "KILLSWITCH_ACTIVE" in str(res2.error)


def test_below_80pct_does_not_activate_killswitch(tmp_path) -> None:
    """79% of budget should NOT trigger the auto-killswitch threshold."""
    ks = KillSwitch(state_file=tmp_path / "ks.json")
    limits = RiskLimits(daily_loss_limit="0.90")  # raise daily_loss_limit so it doesn't interfere
    snap = RiskSnapshot(
        monthly_budget="1000.00",
        expected_spend_rate_4h="10.00",
        actual_spend_4h="5.00",
        daily_loss="790.00",  # 79% — below 80% threshold
    )

    res = check_safety_before_spend(
        Decimal("10.00"),
        "op_79pct",
        killswitch=ks,
        risk_snapshot=snap,
        risk_limits=limits,
    )
    assert isinstance(res, Ok)
    assert not ks.is_active(KillSwitchLevel.SYSTEM)
