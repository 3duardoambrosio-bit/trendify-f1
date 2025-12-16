from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Protocol

from vault.vault_v1 import VaultV1, SpendResult
from vault.cashflow_v1 import CashFlowState


class LedgerLike(Protocol):
    def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    vault_reason: str
    cashflow_ok: bool


class SpendPolicyV1:
    """
    Orquestador P0:
    - Vault = reglas duras (caps / reserve / fondos)
    - CashFlow = liquidez real (evita morirte por holds/refunds)
    - Ledger (opcional) = auditoría
    """
    def __init__(self, vault: VaultV1, cashflow: CashFlowState, ledger: Optional[LedgerLike] = None):
        self.vault = vault
        self.cashflow = cashflow
        self.ledger = ledger

    def request(self, *, pool: str, product_id: str, amount: Decimal, day: int, context: Optional[Dict[str, Any]] = None) -> PolicyDecision:
        context = context or {}
        v: SpendResult = self.vault.request_spend(pool=pool, product_id=product_id, amount=amount, day=day)

        # Si Vault ya dijo NO por una razón específica, se respeta (ACERO: razón más concreta gana)
        if not v.allowed:
            self._emit("SPEND_DENIED", {"reason": v.reason, "pool": pool, "product_id": product_id, "amount": str(amount), **context})
            return PolicyDecision(False, v.reason, v.reason, cashflow_ok=self.cashflow.can_spend(amount))

        # Vault permite → ahora sí Cashflow gate (protección contra insolvencia)
        if not self.cashflow.can_spend(amount):
            # rollback v1: reinyectar gasto aprobado (ACERO: no dejamos estado inconsistente)
            # Nota: esto mantiene Vault como autoridad pero evita "gasto fantasma"
            self._rollback_vault(pool=pool, amount=amount, product_id=product_id)
            self._emit("SPEND_DENIED", {"reason": "CASHFLOW_GUARD", "pool": pool, "product_id": product_id, "amount": str(amount), **context})
            return PolicyDecision(False, "CASHFLOW_GUARD", v.reason, cashflow_ok=False)

        self._emit("SPEND_APPROVED", {"pool": pool, "product_id": product_id, "amount": str(amount), **context})
        return PolicyDecision(True, "APPROVED", v.reason, cashflow_ok=True)

    def _rollback_vault(self, *, pool: str, amount: Decimal, product_id: str) -> None:
        # rollback mínimo: des-spend en el pool (v1 no tiene ledger transaccional completo aún)
        p = self.vault.pools()[pool]
        p.spent -= amount
        if pool == "learning":
            # revertir tracking por producto
            spent = self.vault._learning_spent_by_product.get(product_id, Decimal("0"))
            self.vault._learning_spent_by_product[product_id] = (spent - amount)

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.ledger is None:
            return
        self.ledger.emit(event_type, payload)