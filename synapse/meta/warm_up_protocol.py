# V3GAP:warm_up_executed_10_days

# V3GAP:B-04_warm_up_protocol

from __future__ import annotations

"""
Meta Warm-Up Protocol — B-04.

Regla: Cuenta nueva NO puede gastar >$5 USD/día los primeros 3 días.
Después escala 20%/día hasta alcanzar el daily cap configurado.

__MARKER__ embedded in module constant below.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging

import deal

__MARKER__ = "SESSION_S10_warm_up_protocol_20260228"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WarmUpConfig:
    initial_daily_usd: Decimal = Decimal("5")
    ramp_pct: Decimal = Decimal("0.20")
    min_account_age_days: int = 10
    ramp_start_day: int = 3


class WarmUpProtocol:
    def __init__(self, config: WarmUpConfig, account_created_at: datetime | None):
        self._config = config
        self._account_created_at = account_created_at
        self._blocked = self._is_blocked_created_at(account_created_at)

    @staticmethod
    def _is_blocked_created_at(dt: datetime | None) -> bool:
        if dt is None:
            return True
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > now

    def _account_age_days(self) -> int:
        assert self._account_created_at is not None
        now = datetime.now(timezone.utc)
        created = self._account_created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = now.date() - created.date()
        return max(int(delta.days), 0)

    def get_current_day(self) -> int:
        """
        Día operativo desde account_created_at (1-indexed).
        Si está bloqueado por fecha futura/None => 0.
        """
        if self._blocked:
            return 0
        return self._account_age_days() + 1

    def is_warm_up_required(self) -> bool:
        if self._blocked:
            return True
        return self._account_age_days() < self._config.min_account_age_days

    @deal.pre(lambda self, day, daily_cap=None: day > 0)
    @deal.post(lambda result: result >= Decimal("0"))
    @deal.ensure(lambda self, day, daily_cap=None, result=None: (daily_cap is None) or (result is not None and result <= daily_cap))
    def get_daily_limit(self, day: int, daily_cap: Decimal | None = None) -> Decimal:
        """
        Día 1-3: initial_daily_usd.
        Día 4+: initial * (1 + ramp_pct)^(day - ramp_start_day).

        REGLA CRÍTICA:
        - Si account_created_at es None o futuro => BLOQUEAR => Decimal("0")
        """
        if self._blocked:
            log.warning("Warm-up blocked: account_created_at is None or in the future.")
            return Decimal("0")

        initial = self._config.initial_daily_usd
        ramp = self._config.ramp_pct
        ramp_start = self._config.ramp_start_day

        if day <= ramp_start:
            limit = initial
        else:
            exponent = int(day - ramp_start)
            base = (Decimal("1") + ramp)
            limit = initial * (base ** exponent)

        limit = limit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if daily_cap is not None:
            limit = min(limit, daily_cap)

        if limit < Decimal("0"):
            return Decimal("0")

        return limit