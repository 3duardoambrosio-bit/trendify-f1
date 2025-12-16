from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class Hold:
    amount: Decimal
    release_in_days: int  # 0 = hoy


@dataclass
class CashflowV1:
    """
    Cashflow minimalista pero real:
    - available_cash: lo gastable hoy
    - holds: dinero vendido pero no liberado por pasarela
    - projected_refunds: buffer conservador (no optimista)
    """
    available_cash: Decimal
    holds: List[Hold] = field(default_factory=list)
    projected_refunds: Decimal = Decimal("0")
    safety_buffer: Decimal = Decimal("10")  # no bajamos de esto

    def projected_available_in(self, days: int) -> Decimal:
        days = int(days)
        releasing = sum(h.amount for h in self.holds if h.release_in_days <= days)
        v = self.available_cash + releasing - self.projected_refunds
        return v

    def runway_days(self, burn_per_day: Decimal) -> int:
        burn_per_day = _d(burn_per_day)
        if burn_per_day <= 0:
            return 9999
        cash = self.projected_available_in(0) - self.safety_buffer
        if cash <= 0:
            return 0
        return int((cash / burn_per_day).to_integral_value(rounding="ROUND_FLOOR"))

    def can_spend_today(self, amount: Decimal) -> bool:
        amount = _d(amount)
        after = self.projected_available_in(0) - amount
        return after >= self.safety_buffer