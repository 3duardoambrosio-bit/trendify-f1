"""S19.1 P0 test: circuit breaker trips on real API errors, not just AttributeError."""

from __future__ import annotations

import pytest

from synapse.infra.circuit_breaker import CircuitBreaker, CircuitOpenError


def test_trips_on_connection_error():
    """ConnectionError (e.g. Meta API down) must count as failure."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=9999)
    for _ in range(3):
        with pytest.raises(ConnectionError):
            cb.call(lambda: (_ for _ in ()).throw(ConnectionError("network_down")))
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "should_not_reach")


def test_trips_on_timeout_error():
    """TimeoutError (e.g. Dropi slow) must count as failure."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=9999)
    for _ in range(3):
        with pytest.raises(TimeoutError):
            cb.call(lambda: (_ for _ in ()).throw(TimeoutError("read_timeout")))
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "should_not_reach")


def test_trips_on_runtime_error():
    """RuntimeError (e.g. HTTP 500 mapped) must count as failure."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=9999)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("http_500")))
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "should_not_reach")


def test_trips_on_value_error():
    """ValueError (e.g. invalid API response) must count as failure."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=9999)
    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("bad_json")))
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "should_not_reach")


def test_still_trips_on_attribute_error():
    """AttributeError must still work (backward compat)."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=9999)
    for _ in range(3):
        with pytest.raises(AttributeError):
            cb.call(lambda: (_ for _ in ()).throw(AttributeError("old_behavior")))
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "should_not_reach")


def test_resets_on_success():
    """After failures, a success resets the counter."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=9999)
    # 2 failures (not enough to open)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))
    # 1 success resets
    result = cb.call(lambda: "ok")
    assert result == "ok"
    assert cb._failures == 0
    # 2 more failures still not enough
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(lambda: (_ for _ in ()).throw(ConnectionError("fail")))
    # Circuit still closed
    result = cb.call(lambda: "still_ok")
    assert result == "still_ok"


def test_mixed_exception_types_accumulate():
    """Different exception types all count toward the threshold."""
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=9999)
    with pytest.raises(ConnectionError):
        cb.call(lambda: (_ for _ in ()).throw(ConnectionError("one")))
    with pytest.raises(TimeoutError):
        cb.call(lambda: (_ for _ in ()).throw(TimeoutError("two")))
    with pytest.raises(ValueError):
        cb.call(lambda: (_ for _ in ()).throw(ValueError("three")))
    # 3 different types = circuit open
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "blocked")
