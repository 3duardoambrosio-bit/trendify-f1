"""Simple circuit breaker. AUTO: F1_CORE_BOOTSTRAP_2026_02 + S19.1 P0 fix."""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")

class CircuitOpenError(RuntimeError):
    pass

@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout_s: float = 30.0
    _failures: int = 0
    _opened_at: float | None = None

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if (time.time() - self._opened_at) >= self.reset_timeout_s:
            return False
        return True

    def call(self, fn: Callable[[], T]) -> T:
        if self._is_open():
            raise CircuitOpenError("circuit_open")
        try:
            out = fn()
            self._failures = 0
            self._opened_at = None
            return out
        except Exception:
            # S19.1 P0 FIX: was `except (AttributeError)` which meant
            # HTTP 500, timeouts, ConnectionError etc. never counted
            # as failures. Now ANY exception trips the breaker.
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.time()
            raise
