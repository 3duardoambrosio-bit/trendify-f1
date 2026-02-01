from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta, timezone


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitConfig:
    failure_threshold: int = 3
    success_threshold: int = 1
    cooldown_seconds: int = 60       # initial cooldown (was 3600 fixed)
    max_cooldown_seconds: int = 3600  # cap for exponential backoff


class CircuitBreaker:
    """
    Circuit breaker with optional file-backed persistence and exponential backoff.

    Without state_file: pure in-memory (backwards compatible).
    With state_file: survives process restarts via atomic JSON writes.
    """
    def __init__(self, config: CircuitConfig = CircuitConfig(), *, state_file: Optional[Path] = None) -> None:
        self.config = config
        self.state: CircuitState = CircuitState.CLOSED
        self.failures: int = 0
        self.successes: int = 0
        self.last_failure_at: Optional[datetime] = None
        self._current_cooldown: int = config.cooldown_seconds
        self._state_file = Path(state_file) if state_file else None
        if self._state_file is not None:
            self._load_state()

    def record_failure(self) -> None:
        self.failures += 1
        self.successes = 0
        self.last_failure_at = datetime.now(timezone.utc)
        if self.state == CircuitState.CLOSED and self.failures >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            # Exponential backoff on re-open from HALF_OPEN
            self._current_cooldown = min(
                self._current_cooldown * 2,
                self.config.max_cooldown_seconds,
            )
        self._persist()

    def record_success(self) -> None:
        self.successes += 1
        self.failures = 0
        if self.state == CircuitState.HALF_OPEN and self.successes >= self.config.success_threshold:
            self.state = CircuitState.CLOSED
            # Reset cooldown on full recovery
            self._current_cooldown = self.config.cooldown_seconds
        self._persist()

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self._cooldown_elapsed():
                self.state = CircuitState.HALF_OPEN
                self._persist()
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def _cooldown_elapsed(self) -> bool:
        if not self.last_failure_at:
            return True
        now = datetime.now(timezone.utc)
        # Handle naive datetimes loaded from old state
        lf = self.last_failure_at
        if lf.tzinfo is None:
            lf = lf.replace(tzinfo=timezone.utc)
        return (now - lf) >= timedelta(seconds=self._current_cooldown)

    # --- Persistence ---

    def _persist(self) -> None:
        if self._state_file is None:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "state": self.state.value,
            "failures": self.failures,
            "successes": self.successes,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
            "current_cooldown": self._current_cooldown,
        }
        self._atomic_write(data)

    def _atomic_write(self, data: dict) -> None:
        """Write JSON atomically: write to .tmp, fsync, then os.replace."""
        assert self._state_file is not None
        tmp_path = self._state_file.with_suffix(".tmp")
        content = json.dumps(data, ensure_ascii=False, indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(self._state_file))

    def _load_state(self) -> None:
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            self.state = CircuitState(raw["state"])
            self.failures = int(raw.get("failures", 0))
            self.successes = int(raw.get("successes", 0))
            lf = raw.get("last_failure_at")
            self.last_failure_at = datetime.fromisoformat(lf) if lf else None
            self._current_cooldown = int(raw.get("current_cooldown", self.config.cooldown_seconds))
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupted state file — start clean, don't crash
            pass
