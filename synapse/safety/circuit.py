from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import deal

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitConfig:
    failure_threshold: int = 3
    success_threshold: int = 1
    cooldown_seconds: int = 60
    max_cooldown_seconds: int = 3600


class CircuitBreaker:
    """
    Circuit breaker with optional file-backed persistence and exponential backoff.

    Backwards-compat:
    - cooldown_seconds may be 0 to represent "immediate" cooldown.
    """

    @deal.pre(lambda self, config=CircuitConfig(), state_file=None: config is not None, message="config required")
    @deal.pre(lambda self, config=CircuitConfig(), state_file=None: config.failure_threshold > 0, message="failure_threshold > 0")
    @deal.pre(lambda self, config=CircuitConfig(), state_file=None: config.success_threshold > 0, message="success_threshold > 0")
    @deal.pre(lambda self, config=CircuitConfig(), state_file=None: config.cooldown_seconds >= 0, message="cooldown_seconds >= 0")
    @deal.pre(
        lambda self, config=CircuitConfig(), state_file=None: config.max_cooldown_seconds >= config.cooldown_seconds,
        message="max_cooldown_seconds >= cooldown_seconds",
    )
    @deal.post(lambda result: result is None, message="__init__ returns None")
    @deal.raises(deal.PreContractError, deal.RaisesContractError)
    def __init__(self: CircuitBreaker, config: CircuitConfig = CircuitConfig(), *, state_file: Optional[Path] = None) -> None:
        self.config: CircuitConfig = config
        self.state: CircuitState = CircuitState.CLOSED
        self.failures: int = 0
        self.successes: int = 0
        self.last_failure_at: Optional[datetime] = None
        self._current_cooldown: int = config.cooldown_seconds
        self._state_file: Optional[Path] = Path(state_file) if state_file else None
        if self._state_file is not None:
            self._load_state()

    @deal.pre(lambda self: True, message="record_failure contract")
    @deal.post(lambda result: result is None, message="record_failure returns None")
    @deal.raises(deal.PreContractError, deal.RaisesContractError)
    def record_failure(self: CircuitBreaker) -> None:
        self.failures += 1
        self.successes = 0
        self.last_failure_at = datetime.now(timezone.utc)

        if self.state == CircuitState.CLOSED and self.failures >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self._current_cooldown = min(self._current_cooldown * 2, self.config.max_cooldown_seconds)

        self._persist()

    @deal.pre(lambda self: True, message="record_success contract")
    @deal.post(lambda result: result is None, message="record_success returns None")
    @deal.raises(deal.PreContractError, deal.RaisesContractError)
    def record_success(self: CircuitBreaker) -> None:
        self.successes += 1
        self.failures = 0

        if self.state == CircuitState.HALF_OPEN and self.successes >= self.config.success_threshold:
            self.state = CircuitState.CLOSED
            self._current_cooldown = self.config.cooldown_seconds

        self._persist()

    @deal.pre(lambda self: True, message="can_execute contract")
    @deal.post(lambda result: isinstance(result, bool), message="can_execute returns bool")
    @deal.raises(deal.PreContractError, deal.RaisesContractError)
    def can_execute(self: CircuitBreaker) -> bool:
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

        lf = self.last_failure_at
        if lf.tzinfo is None:
            lf = lf.replace(tzinfo=timezone.utc)

        return (now - lf) >= timedelta(seconds=self._current_cooldown)

    # --- Persistence (private) ---

    def _persist(self) -> None:
        if self._state_file is None:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.error("circuit persist mkdir failed for %s", self._state_file, exc_info=True)
            return

        data: Dict[str, Any] = {
            "state": self.state.value,
            "failures": self.failures,
            "successes": self.successes,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
            "current_cooldown": self._current_cooldown,
        }
        try:
            self._atomic_write(data)
        except OSError:
            logger.error("circuit atomic write failed for %s", self._state_file, exc_info=True)

    def _atomic_write(self, data: Dict[str, Any]) -> None:
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
            if not isinstance(raw, dict):
                raise ValueError("state must be dict")

            self.state = CircuitState(str(raw["state"]))
            self.failures = int(raw.get("failures", 0))
            self.successes = int(raw.get("successes", 0))
            lf = raw.get("last_failure_at")
            self.last_failure_at = datetime.fromisoformat(str(lf)) if lf else None

            cd = int(raw.get("current_cooldown", self.config.cooldown_seconds))
            if cd < 0:
                cd = self.config.cooldown_seconds
            if cd > self.config.max_cooldown_seconds:
                cd = self.config.max_cooldown_seconds
            self._current_cooldown = cd
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError, TypeError):
            # FAIL-CLOSED: corrupted state -> OPEN with max cooldown (block execution)
            self.state = CircuitState.OPEN
            self.failures = self.config.failure_threshold
            self.successes = 0
            self.last_failure_at = datetime.now(timezone.utc)
            self._current_cooldown = getattr(self.config, "max_cooldown_seconds")
            logger.critical("circuit state corrupted at %s; FAIL-CLOSED -> OPEN", self._state_file, exc_info=True)
