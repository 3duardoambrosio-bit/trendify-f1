from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional, Tuple


def _d(x: str | int | float | Decimal) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class SpendResult:
    allowed: bool
    reason: str
    pool: str
    amount: Decimal
    product_id: str


@dataclass
class BudgetPool:
    name: str
    total: Decimal
    spent: Decimal = Decimal("0")

    @property
    def available(self) -> Decimal:
        a = self.total - self.spent
        return a if a > 0 else Decimal("0")


@dataclass
class VaultV1:
    """
    Vault 3 budgets:
      - learning: para experiments
      - operational: para operar lo que ya probó señal
      - reserve: INTOCABLE (solo admin)
    """
    learning: BudgetPool
    operational: BudgetPool
    reserve: BudgetPool

    # caps de seguridad
    max_learning_per_product_total: Decimal = Decimal("30")
    max_learning_per_product_day1: Decimal = Decimal("10")

    # tracking mínimo por producto (en memoria v1; luego persistimos/ledger)
    _learning_spent_by_product: Dict[str, Decimal] = field(default_factory=dict)

    def pools(self) -> Dict[str, BudgetPool]:
        return {"learning": self.learning, "operational": self.operational, "reserve": self.reserve}

    def request_spend(self, *, pool: str, product_id: str, amount: Decimal, day: int = 1) -> SpendResult:
        amount = _d(amount)
        if amount <= 0:
            return SpendResult(False, "AMOUNT_NON_POSITIVE", pool, amount, product_id)

        if pool not in ("learning", "operational", "reserve"):
            return SpendResult(False, "UNKNOWN_POOL", pool, amount, product_id)

        # Reserve: nunca por automático
        if pool == "reserve":
            return SpendResult(False, "RESERVE_PROTECTED", pool, amount, product_id)

        p = self.pools()[pool]
        if amount > p.available:
            return SpendResult(False, "INSUFFICIENT_POOL_FUNDS", pool, amount, product_id)

        # Caps (solo aplican a Learning)
        if pool == "learning":
            spent = self._learning_spent_by_product.get(product_id, Decimal("0"))
            if day == 1 and (spent + amount) > self.max_learning_per_product_day1:
                return SpendResult(False, "DAY1_CAP_REACHED", pool, amount, product_id)
            if (spent + amount) > self.max_learning_per_product_total:
                return SpendResult(False, "PRODUCT_TOTAL_CAP_REACHED", pool, amount, product_id)

        # approve + mutate state (v1)
        p.spent += amount
        if pool == "learning":
            self._learning_spent_by_product[product_id] = self._learning_spent_by_product.get(product_id, Decimal("0")) + amount

        return SpendResult(True, "APPROVED", pool, amount, product_id)

    def admin_move_to_reserve(self, amount: Decimal) -> None:
        """ÚNICA forma de tocar reserve: manual/admin. (No usado por autopilot)."""
        amount = _d(amount)
        if amount <= 0:
            return
        # mover desde operational si hay
        take = min(amount, self.operational.available)
        self.operational.spent += take
        self.reserve.total += take