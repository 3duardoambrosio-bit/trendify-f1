from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal


PoolName = Literal["learning", "operational", "reserve"]


def D(x: str | int | float | Decimal) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


@dataclass(frozen=True)
class SpendDecision:
    allowed: bool
    pool: PoolName
    amount: Decimal
    reason: str


@dataclass(frozen=True)
class BudgetPool:
    name: PoolName
    total: Decimal
    spent: Decimal = Decimal("0")

    @property
    def available(self) -> Decimal:
        return (self.total - self.spent).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class VaultP0:
    """
    3-pool Vault.
    - reserve is protected (no spend via request_spend)
    - request_spend only works for learning/operational
    """

    def __init__(
        self,
        *,
        total_budget: Decimal,
        learning_pct: Decimal = Decimal("0.30"),
        operational_pct: Decimal = Decimal("0.55"),
        reserve_pct: Decimal = Decimal("0.15"),
    ) -> None:
        tb = D(total_budget).quantize(Decimal("0.01"))
        lp, op, rp = D(learning_pct), D(operational_pct), D(reserve_pct)

        if (lp + op + rp) != Decimal("1.00"):
            raise ValueError("learning_pct + operational_pct + reserve_pct must equal 1.00")

        learning = (tb * lp).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        operational = (tb * op).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reserve = (tb - learning - operational).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        self.learning = BudgetPool("learning", learning)
        self.operational = BudgetPool("operational", operational)
        self.reserve = BudgetPool("reserve", reserve)

    @property
    def total(self) -> Decimal:
        return (self.learning.total + self.operational.total + self.reserve.total).quantize(Decimal("0.01"))

    def request_spend(self, *, pool: PoolName, amount: Decimal) -> SpendDecision:
        amt = D(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if amt <= 0:
            return SpendDecision(False, pool, amt, "amount_must_be_positive")

        if pool == "reserve":
            return SpendDecision(False, pool, amt, "reserve_protected")

        target = self.learning if pool == "learning" else self.operational

        if amt > target.available:
            return SpendDecision(False, pool, amt, "insufficient_funds")

        # NOTE: immutable pools -> return "virtual approval".
        return SpendDecision(True, pool, amt, "approved")