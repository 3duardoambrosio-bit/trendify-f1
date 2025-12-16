from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class CashflowState:
    """
    Minimal cashflow model.
    - available_cash: money you can spend now
    - held_cash: money locked by processors (Shopify/PayPal holds)
    - projected_refunds/chargebacks: conservative deductions
    """
    available_cash: Decimal
    held_cash: Decimal = Decimal("0")
    projected_refunds: Decimal = Decimal("0")
    projected_chargebacks: Decimal = Decimal("0")

    @property
    def effective_available(self) -> Decimal:
        v = D(self.available_cash) - D(self.projected_refunds) - D(self.projected_chargebacks)
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def can_spend(self, amount: Decimal, safety_buffer: Decimal) -> bool:
        amt = D(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        buf = D(safety_buffer).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amt <= 0:
            return False
        return (self.effective_available - amt) >= buf

    def runway_days(self, daily_burn: Decimal) -> int:
        burn = D(daily_burn).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if burn <= 0:
            return 10**9
        days = int((self.effective_available / burn).to_integral_value(rounding=ROUND_HALF_UP))
        return max(days, 0)