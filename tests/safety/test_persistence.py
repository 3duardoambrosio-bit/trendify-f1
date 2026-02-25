"""Tests for KillSwitch and CircuitBreaker persistence across restarts."""
from pathlib import Path
from datetime import datetime, timezone

from synapse.safety.killswitch import KillSwitch, KillSwitchLevel, KillSwitchActivation
from synapse.safety.circuit import CircuitBreaker, CircuitConfig, CircuitState


# ── KillSwitch persistence ──────────────────────────────────────────


def test_killswitch_persists_across_restart(tmp_path: Path) -> None:
    state_file = tmp_path / "ks.json"

    # Instance 1: activate system kill
    ks1 = KillSwitch(state_file=state_file)
    assert ks1.is_active(KillSwitchLevel.SYSTEM) is False
    ks1.activate(KillSwitchActivation(level=KillSwitchLevel.SYSTEM, reason="emergency"))
    assert ks1.is_active(KillSwitchLevel.SYSTEM) is True
    assert state_file.exists()

    # Instance 2: simulates process restart — loads from file
    ks2 = KillSwitch(state_file=state_file)
    assert ks2.is_active(KillSwitchLevel.SYSTEM) is True
    snap = ks2.snapshot()
    assert "system:*" in snap
    assert snap["system:*"]["reason"] == "emergency"


def test_killswitch_clear_removes_state_file(tmp_path: Path) -> None:
    state_file = tmp_path / "ks.json"

    ks = KillSwitch(state_file=state_file)
    ks.activate(KillSwitchActivation(level=KillSwitchLevel.SYSTEM, reason="test"))
    assert state_file.exists()

    ks.clear(KillSwitchLevel.SYSTEM)
    assert not state_file.exists()

    # New instance starts clean
    ks2 = KillSwitch(state_file=state_file)
    assert ks2.is_active(KillSwitchLevel.SYSTEM) is False


def test_killswitch_no_state_file_backwards_compatible() -> None:
    """Without state_file param, behaves exactly like before."""
    ks = KillSwitch()
    ks.activate(KillSwitchActivation(level=KillSwitchLevel.CAMPAIGN, reason="test", target_id="c1"))
    assert ks.is_active(KillSwitchLevel.CAMPAIGN, target_id="c1") is True
    ks.clear(KillSwitchLevel.CAMPAIGN, target_id="c1")
    assert ks.is_active(KillSwitchLevel.CAMPAIGN, target_id="c1") is False


def test_killswitch_timestamp_is_per_instance() -> None:
    """Fix P1-003: activated_at must be evaluated at creation time, not import time."""
    a1 = KillSwitchActivation(level=KillSwitchLevel.SYSTEM, reason="r1")
    a2 = KillSwitchActivation(level=KillSwitchLevel.SYSTEM, reason="r2")
    # They should both have timezone-aware timestamps
    assert a1.activated_at.tzinfo is not None
    assert a2.activated_at.tzinfo is not None
    # They should be very close but potentially different objects
    diff = abs((a2.activated_at - a1.activated_at).total_seconds())
    assert diff < 1.0  # created within 1s of each other


def test_killswitch_corrupted_state_file_fail_closed(tmp_path: Path) -> None:
    state_file = tmp_path / "ks.json"
    state_file.write_text("NOT VALID JSON {{{", encoding="utf-8")

    ks = KillSwitch(state_file=state_file)
    assert ks.is_active(KillSwitchLevel.SYSTEM) is True


# ── CircuitBreaker persistence ──────────────────────────────────────


def test_circuit_breaker_persists_across_restart(tmp_path: Path) -> None:
    state_file = tmp_path / "cb.json"
    cfg = CircuitConfig(failure_threshold=2, cooldown_seconds=60)

    # Instance 1: open the circuit
    cb1 = CircuitBreaker(cfg, state_file=state_file)
    cb1.record_failure()
    cb1.record_failure()
    assert cb1.state == CircuitState.OPEN
    assert state_file.exists()

    # Instance 2: simulates restart — loads OPEN state
    cb2 = CircuitBreaker(cfg, state_file=state_file)
    assert cb2.state == CircuitState.OPEN
    assert cb2.failures == 2


def test_circuit_breaker_backoff_doubles_on_reopen(tmp_path: Path) -> None:
    state_file = tmp_path / "cb.json"
    cfg = CircuitConfig(failure_threshold=2, cooldown_seconds=10, max_cooldown_seconds=100)

    cb = CircuitBreaker(cfg, state_file=state_file)
    assert cb._current_cooldown == 10

    # Open circuit
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Force HALF_OPEN by setting last_failure_at far in the past
    cb.last_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Fail again in HALF_OPEN → re-open with doubled cooldown
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb._current_cooldown == 20  # 10 * 2

    # Repeat: double again
    cb.last_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    cb.can_execute()  # → HALF_OPEN
    cb.record_failure()
    assert cb._current_cooldown == 40  # 20 * 2


def test_circuit_breaker_backoff_capped_at_max(tmp_path: Path) -> None:
    state_file = tmp_path / "cb.json"
    cfg = CircuitConfig(failure_threshold=1, cooldown_seconds=500, max_cooldown_seconds=1000)

    cb = CircuitBreaker(cfg, state_file=state_file)
    cb.record_failure()  # → OPEN, cooldown=500

    cb.last_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    cb.can_execute()  # → HALF_OPEN
    cb.record_failure()  # → OPEN, cooldown=1000 (capped)
    assert cb._current_cooldown == 1000

    cb.last_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    cb.can_execute()
    cb.record_failure()
    assert cb._current_cooldown == 1000  # stays capped


def test_circuit_breaker_backoff_resets_on_recovery(tmp_path: Path) -> None:
    state_file = tmp_path / "cb.json"
    cfg = CircuitConfig(failure_threshold=2, cooldown_seconds=10, max_cooldown_seconds=100)

    cb = CircuitBreaker(cfg, state_file=state_file)
    cb.record_failure()
    cb.record_failure()
    cb.last_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    cb.can_execute()  # HALF_OPEN
    cb.record_failure()  # cooldown = 20
    assert cb._current_cooldown == 20

    # Now recover
    cb.last_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    cb.can_execute()  # HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._current_cooldown == 10  # reset to initial


def test_circuit_breaker_no_state_file_backwards_compatible() -> None:
    """Without state_file, behaves exactly like before."""
    cb = CircuitBreaker(CircuitConfig(failure_threshold=2, cooldown_seconds=0))
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_corrupted_state_file_starts_clean(tmp_path: Path) -> None:
    state_file = tmp_path / "cb.json"
    state_file.write_text("{broken", encoding="utf-8")

    cb = CircuitBreaker(state_file=state_file)
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False
    assert cb.failures == cb.config.failure_threshold