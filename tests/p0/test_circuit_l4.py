from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta, timezone

from hypothesis import given, strategies as st

from synapse.safety.circuit import CircuitBreaker, CircuitConfig, CircuitState


FT = st.integers(min_value=1, max_value=5)
STH = st.integers(min_value=1, max_value=3)
CD = st.integers(min_value=1, max_value=10)
MAXCD_RAW = st.integers(min_value=1, max_value=60)


@given(FT, STH, CD, MAXCD_RAW)
def test_init_closed_and_can_execute(ft: int, sth: int, cd: int, maxcd_raw: int) -> None:
    maxcd = max(cd, maxcd_raw)
    cfg = CircuitConfig(failure_threshold=ft, success_threshold=sth, cooldown_seconds=cd, max_cooldown_seconds=maxcd)
    cb = CircuitBreaker(cfg)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


@given(FT, CD, MAXCD_RAW)
def test_record_failure_opens_at_threshold(ft: int, cd: int, maxcd_raw: int) -> None:
    maxcd = max(cd, maxcd_raw)
    cfg = CircuitConfig(failure_threshold=ft, success_threshold=1, cooldown_seconds=cd, max_cooldown_seconds=maxcd)
    cb = CircuitBreaker(cfg)

    for _ in range(ft):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


@given(FT, CD, MAXCD_RAW)
def test_can_execute_moves_to_half_open_after_cooldown(ft: int, cd: int, maxcd_raw: int) -> None:
    maxcd = max(cd, maxcd_raw)
    cfg = CircuitConfig(failure_threshold=ft, success_threshold=1, cooldown_seconds=cd, max_cooldown_seconds=maxcd)
    cb = CircuitBreaker(cfg)

    for _ in range(ft):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN
    cb.last_failure_at = datetime.now(timezone.utc) - timedelta(seconds=cb._current_cooldown + 1)  # type: ignore[attr-defined]
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN


@given(FT, STH, CD, MAXCD_RAW)
def test_record_success_closes_after_threshold(ft: int, sth: int, cd: int, maxcd_raw: int) -> None:
    maxcd = max(cd, maxcd_raw)
    cfg = CircuitConfig(failure_threshold=ft, success_threshold=sth, cooldown_seconds=cd, max_cooldown_seconds=maxcd)
    cb = CircuitBreaker(cfg)

    for _ in range(ft):
        cb.record_failure()

    cb.last_failure_at = datetime.now(timezone.utc) - timedelta(seconds=cb._current_cooldown + 1)  # type: ignore[attr-defined]
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    for _ in range(sth):
        cb.record_success()

    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


@given(FT, CD)
def test_half_open_failure_reopens_and_backoff(ft: int, cd: int) -> None:
    cfg = CircuitConfig(failure_threshold=ft, success_threshold=1, cooldown_seconds=cd, max_cooldown_seconds=max(cd, 16))
    cb = CircuitBreaker(cfg)

    for _ in range(ft):
        cb.record_failure()

    cb.last_failure_at = datetime.now(timezone.utc) - timedelta(seconds=cb._current_cooldown + 1)  # type: ignore[attr-defined]
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    before = cb._current_cooldown  # type: ignore[attr-defined]
    cb.record_failure()
    after = cb._current_cooldown  # type: ignore[attr-defined]

    assert cb.state == CircuitState.OPEN
    assert after >= before
    assert after <= cfg.max_cooldown_seconds


@given(FT, STH, CD, MAXCD_RAW)
def test_persistence_roundtrip(ft: int, sth: int, cd: int, maxcd_raw: int) -> None:
    maxcd = max(cd, maxcd_raw)
    cfg = CircuitConfig(failure_threshold=ft, success_threshold=sth, cooldown_seconds=cd, max_cooldown_seconds=maxcd)

    with TemporaryDirectory() as td:
        state_file = Path(td) / "circuit_state.json"
        cb1 = CircuitBreaker(cfg, state_file=state_file)

        for _ in range(ft):
            cb1.record_failure()

        cb2 = CircuitBreaker(cfg, state_file=state_file)
        assert cb2.state == cb1.state
        assert cb2.failures == cb1.failures


def test_corrupted_state_does_not_crash() -> None:
    cfg = CircuitConfig()
    with TemporaryDirectory() as td:
        state_file = Path(td) / "circuit_state.json"
        state_file.write_text("{not valid json", encoding="utf-8")
        cb = CircuitBreaker(cfg, state_file=state_file)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True