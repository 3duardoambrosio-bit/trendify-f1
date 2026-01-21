from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime, timedelta


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitConfig:
    failure_threshold: int = 3
    success_threshold: int = 1
    cooldown_seconds: int = 3600  # 1h


class CircuitBreaker:
    def __init__(self, config: CircuitConfig = CircuitConfig()) -> None:
        self.config = config
        self.state: CircuitState = CircuitState.CLOSED
        self.failures: int = 0
        self.successes: int = 0
        self.last_failure_at: Optional[datetime] = None

    def record_failure(self) -> None:
        self.failures += 1
        self.successes = 0
        self.last_failure_at = datetime.utcnow()
        if self.state == CircuitState.CLOSED and self.failures >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN

    def record_success(self) -> None:
        self.successes += 1
        self.failures = 0
        if self.state == CircuitState.HALF_OPEN and self.successes >= self.config.success_threshold:
            self.state = CircuitState.CLOSED

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self._cooldown_elapsed():
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def _cooldown_elapsed(self) -> bool:
        if not self.last_failure_at:
            return True
        return (datetime.utcnow() - self.last_failure_at) >= timedelta(seconds=self.config.cooldown_seconds)
