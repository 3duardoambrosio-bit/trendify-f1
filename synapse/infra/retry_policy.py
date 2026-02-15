"""Central retry policy with exponential backoff + jitter. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar, Tuple

T = TypeVar("T")

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay_s: float
    max_delay_s: float

    def run(self, fn: Callable[[], T], retry_on: Tuple[type, ...] = (Exception,)) -> T:
        attempt = 0
        last_err: Exception | None = None
        while attempt < self.max_attempts:
            attempt += 1
            try:
                return fn()
            except retry_on as e:
                last_err = e
                if attempt >= self.max_attempts:
                    raise
                exp = self.base_delay_s * (2 ** (attempt - 1))
                delay = min(self.max_delay_s, exp)
                delay = delay * (0.7 + random.random() * 0.6)
                time.sleep(delay)
        raise last_err or RuntimeError("retry_policy_failed")
