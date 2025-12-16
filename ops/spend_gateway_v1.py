from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional, Dict, Any

from infra.ledger_ndjson import LedgerNDJSON
from vault.vault_p0 import VaultP0
from vault.cashflow_v1 import CashflowState


PoolName = Literal["learning", "operational", "reserve"]


@dataclass(frozen=True)
class SpendResult:
    allowed: bool
    reason: str
    pool: PoolName
    amount: Decimal
    trace_id: str


class SpendGatewayV1:
    """
    Single choke point for spending approvals.
    Writes ledger events for:
    - SPEND_REQUESTED
    - SPEND_APPROVED / SPEND_DENIED
    """

    def __init__(self, *, ledger: LedgerNDJSON, vault: VaultP0, cashflow: CashflowState, safety_buffer: Decimal) -> None:
        self.ledger = ledger
        self.vault = vault
        self.cashflow = cashflow
        self.safety_buffer = safety_buffer

    def request_spend(
        self,
        *,
        product_id: str,
        pool: PoolName,
        amount: Decimal,
        meta: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> SpendResult:
        ev_req = self.ledger.write(
            event_type="SPEND_REQUESTED",
            entity_type="product",
            entity_id=product_id,
            payload={"pool": pool, "amount": str(amount), "meta": meta or {}},
            trace_id=trace_id,
        )

        # cashflow guardrail (pre-check)
        if not self.cashflow.can_spend(amount, self.safety_buffer):
            self.ledger.write(
                event_type="SPEND_DENIED",
                entity_type="product",
                entity_id=product_id,
                payload={"reason": "cashflow_buffer", "pool": pool, "amount": str(amount)},
                trace_id=ev_req.trace_id,
            )
            return SpendResult(False, "cashflow_buffer", pool, amount, ev_req.trace_id)

        # vault guardrail
        decision = self.vault.request_spend(pool=pool, amount=amount)
        if not decision.allowed:
            self.ledger.write(
                event_type="SPEND_DENIED",
                entity_type="product",
                entity_id=product_id,
                payload={"reason": decision.reason, "pool": pool, "amount": str(amount)},
                trace_id=ev_req.trace_id,
            )
            return SpendResult(False, decision.reason, pool, amount, ev_req.trace_id)

        self.ledger.write(
            event_type="SPEND_APPROVED",
            entity_type="product",
            entity_id=product_id,
            payload={"pool": pool, "amount": str(amount)},
            trace_id=ev_req.trace_id,
        )
        return SpendResult(True, "approved", pool, amount, ev_req.trace_id)