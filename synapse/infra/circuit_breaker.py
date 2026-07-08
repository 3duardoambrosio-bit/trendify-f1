"""Canonical infra circuit breaker. AUTO: F1_CORE_BOOTSTRAP_2026_02 + S19.1 P0 + CB-CONV."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when the circuit is open and the call must not execute."""


class CircuitBreaker:
    """
    Canonical infra circuit breaker.

    Compatibility contracts:
    - accepts threshold/recovery_timeout_s OR failure_threshold/reset_timeout_s
    - exposes state, allow_request, record_failure, record_success
    - keeps call(fn) for wrapper-style execution
    - HALF_OPEN allows exactly one probe request until success/failure resolves it
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
        *,
        threshold: int | None = None,
        recovery_timeout_s: float | None = None,
    ) -> None:
        if threshold is not None:
            failure_threshold = threshold
        if recovery_timeout_s is not None:
            reset_timeout_s = recovery_timeout_s

        if int(failure_threshold) <= 0:
            raise ValueError("failure_threshold/threshold must be > 0")
        if float(reset_timeout_s) < 0:
            raise ValueError("reset_timeout_s/recovery_timeout_s must be >= 0")

        self._failure_threshold = int(failure_threshold)
        self._reset_timeout_s = float(reset_timeout_s)

        self._state = "CLOSED"
        self._failure_count = 0
        self._failures = 0
        self._last_failure_time = 0.0
        self._opened_at: float | None = None
        self._half_open_probe_consumed = False

    @property
    def threshold(self) -> int:
        return self._failure_threshold

    @threshold.setter
    def threshold(self, value: int) -> None:
        if int(value) <= 0:
            raise ValueError("threshold must be > 0")
        self._failure_threshold = int(value)

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @failure_threshold.setter
    def failure_threshold(self, value: int) -> None:
        self.threshold = value

    @property
    def recovery_timeout_s(self) -> float:
        return self._reset_timeout_s

    @recovery_timeout_s.setter
    def recovery_timeout_s(self, value: float) -> None:
        if float(value) < 0:
            raise ValueError("recovery_timeout_s must be >= 0")
        self._reset_timeout_s = float(value)

    @property
    def reset_timeout_s(self) -> float:
        return self._reset_timeout_s

    @reset_timeout_s.setter
    def reset_timeout_s(self, value: float) -> None:
        self.recovery_timeout_s = value

    @property
    def state(self) -> str:
        if self._state == "OPEN" and self._opened_at is not None:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._reset_timeout_s:
                self._state = "HALF_OPEN"
                self._half_open_probe_consumed = False
        return self._state

    def _trip_open(self) -> None:
        now = time.monotonic()
        self._state = "OPEN"
        self._opened_at = now
        self._last_failure_time = now
        self._half_open_probe_consumed = False

    def _reset_closed(self) -> None:
        self._state = "CLOSED"
        self._failure_count = 0
        self._failures = 0
        self._opened_at = None
        self._last_failure_time = 0.0
        self._half_open_probe_consumed = False

    def _is_open(self) -> bool:
        return self.state == "OPEN"

    def record_success(self) -> None:
        self._reset_closed()

    def record_failure(self) -> None:
        current_state = self.state

        if current_state == "HALF_OPEN":
            self._failure_count = self._failure_threshold
            self._failures = self._failure_count
            self._trip_open()
            return

        self._failure_count += 1
        self._failures = self._failure_count
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self._failure_threshold:
            self._trip_open()

    def allow_request(self) -> bool:
        current_state = self.state

        if current_state == "CLOSED":
            return True

        if current_state == "HALF_OPEN":
            if self._half_open_probe_consumed:
                return False
            self._half_open_probe_consumed = True
            return True

        return False

    def call(self, fn: Callable[[], T]) -> T:
        if not self.allow_request():
            raise CircuitOpenError("circuit_open")

        try:
            out = fn()
        except Exception:
            self.record_failure()
            raise

        self.record_success()
        return out