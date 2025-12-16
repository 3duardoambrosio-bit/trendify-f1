from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Tuple


class BudgetType(str, Enum):
    LEARNING = "learning"
    OPERATIONAL = "operational"
    RESERVE = "reserve"


@dataclass(frozen=True)
class VaultConfig:
    total: Decimal
    learning_pct: Decimal = Decimal("0.30")
    operational_pct: Decimal = Decimal("0.55")
    reserve_pct: Decimal = Decimal("0.15")

    def validate(self) -> None:
        s = self.learning_pct + self.operational_pct + self.reserve_pct
        if s != Decimal("1.00"):
            raise ValueError(f"budget pct must sum 1.00, got {s}")


@dataclass(frozen=True)
class BudgetState:
    total: Decimal
    spent: Decimal

    @property
    def available(self) -> Decimal:
        a = self.total - self.spent
        return a if a >= 0 else Decimal("0")


@dataclass(frozen=True)
class VaultState:
    learning: BudgetState
    operational: BudgetState
    reserve: BudgetState

    @property
    def total_available(self) -> Decimal:
        return self.learning.available + self.operational.available + self.reserve.available


@dataclass(frozen=True)
class SpendRequest:
    product_id: str
    amount: Decimal
    budget: BudgetType
    reason: str
    day: int = 1  # for staged caps (optional)


@dataclass(frozen=True)
class SpendDecision:
    allowed: bool
    reason: str
    new_state: Optional[VaultState] = None


class Vault:
    """
    P0 Vault: 3 budgets with hard Reserve protection.
    Reserve can ONLY be modified via explicit admin_deposit/admin_withdraw (not via request_spend).
    """

    def __init__(self, config: VaultConfig) -> None:
        config.validate()
        self.config = config
        self.state = VaultState(
            learning=BudgetState(total=config.total * config.learning_pct, spent=Decimal("0")),
            operational=BudgetState(total=config.total * config.operational_pct, spent=Decimal("0")),
            reserve=BudgetState(total=config.total * config.reserve_pct, spent=Decimal("0")),
        )

    def snapshot(self) -> VaultState:
        return self.state

    def request_spend(self, req: SpendRequest) -> SpendDecision:
        if req.amount <= 0:
            return SpendDecision(False, "amount must be > 0")

        if req.budget == BudgetType.RESERVE:
            return SpendDecision(False, "RESERVE_PROTECTED")

        if req.budget == BudgetType.LEARNING:
            if req.amount > self.state.learning.available:
                return SpendDecision(False, "INSUFFICIENT_LEARNING")
            new = VaultState(
                learning=BudgetState(self.state.learning.total, self.state.learning.spent + req.amount),
                operational=self.state.operational,
                reserve=self.state.reserve,
            )
            self.state = new
            return SpendDecision(True, "APPROVED", new)

        if req.budget == BudgetType.OPERATIONAL:
            if req.amount > self.state.operational.available:
                return SpendDecision(False, "INSUFFICIENT_OPERATIONAL")
            new = VaultState(
                learning=self.state.learning,
                operational=BudgetState(self.state.operational.total, self.state.operational.spent + req.amount),
                reserve=self.state.reserve,
            )
            self.state = new
            return SpendDecision(True, "APPROVED", new)

        return SpendDecision(False, "UNKNOWN_BUDGET")

    # --- Admin ops (explicit, manual) ---
    def admin_deposit(self, amount: Decimal) -> None:
        if amount <= 0:
            raise ValueError("deposit must be > 0")
        cfg = VaultConfig(total=self.config.total + amount,
                          learning_pct=self.config.learning_pct,
                          operational_pct=self.config.operational_pct,
                          reserve_pct=self.config.reserve_pct)
        cfg.validate()
        # Recompute totals; keep spent proportional per bucket? P0: keep spent same; increase totals.
        self.config = cfg
        self.state = VaultState(
            learning=BudgetState(total=cfg.total * cfg.learning_pct, spent=self.state.learning.spent),
            operational=BudgetState(total=cfg.total * cfg.operational_pct, spent=self.state.operational.spent),
            reserve=BudgetState(total=cfg.total * cfg.reserve_pct, spent=self.state.reserve.spent),
        )