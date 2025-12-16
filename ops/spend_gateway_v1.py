from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional, Tuple

from core.ledger import Ledger
from vault.v1 import BudgetType, SpendRequest, SpendDecision, Vault, VaultState


@dataclass(frozen=True)
class ProductCaps:
    max_total_learning: Decimal = Decimal("30")   # hard cap per product in learning
    max_day1_learning: Decimal = Decimal("10")    # staged cap day 1


class SpendGateway:
    """
    Single entry point for spend approvals.
    - Applies per-product caps
    - Calls Vault.request_spend
    - Writes ledger events for approve/deny
    """

    def __init__(self, vault: Vault, ledger: Optional[Ledger] = None, caps: Optional[ProductCaps] = None) -> None:
        self.vault = vault
        self.ledger = ledger or Ledger()
        self.caps = caps or ProductCaps()
        self._product_spent_learning: Dict[str, Decimal] = {}

    def product_spent_learning(self, product_id: str) -> Decimal:
        return self._product_spent_learning.get(product_id, Decimal("0"))

    def request(self, req: SpendRequest) -> SpendDecision:
        # caps apply only to learning (P0)
        if req.budget == BudgetType.LEARNING:
            spent = self.product_spent_learning(req.product_id)
            if (spent + req.amount) > self.caps.max_total_learning:
                dec = SpendDecision(False, "CAP_LEARNING_TOTAL")
                self.ledger.append("SPEND_DENIED", "product", req.product_id, {
                    "budget": req.budget.value, "amount": str(req.amount), "reason": dec.reason,
                    "cap": str(self.caps.max_total_learning), "spent": str(spent)
                })
                return dec

            if req.day == 1 and (spent + req.amount) > self.caps.max_day1_learning:
                dec = SpendDecision(False, "CAP_LEARNING_DAY1")
                self.ledger.append("SPEND_DENIED", "product", req.product_id, {
                    "budget": req.budget.value, "amount": str(req.amount), "reason": dec.reason,
                    "cap": str(self.caps.max_day1_learning), "spent": str(spent), "day": req.day
                })
                return dec

        # Reserve is protected by Vault anyway, but log the attempt.
        if req.budget == BudgetType.RESERVE:
            dec = self.vault.request_spend(req)
            self.ledger.append("SPEND_DENIED", "product", req.product_id, {
                "budget": req.budget.value, "amount": str(req.amount), "reason": dec.reason
            })
            return dec

        dec = self.vault.request_spend(req)
        if dec.allowed:
            if req.budget == BudgetType.LEARNING:
                self._product_spent_learning[req.product_id] = self.product_spent_learning(req.product_id) + req.amount

            self.ledger.append("SPEND_APPROVED", "product", req.product_id, {
                "budget": req.budget.value, "amount": str(req.amount), "reason": dec.reason,
                "day": req.day
            })
        else:
            self.ledger.append("SPEND_DENIED", "product", req.product_id, {
                "budget": req.budget.value, "amount": str(req.amount), "reason": dec.reason,
                "day": req.day
            })
        return dec