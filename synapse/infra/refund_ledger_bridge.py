from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from synapse.infra.idempotency_store import IdempotencyStore
from synapse.infra.ledger_f1_core import Ledger
from synapse.infra.refund_normalizer import RefundEvent


class RefundLedgerBridgeError(RuntimeError):
    """Raised when refund  ledger recording cannot be completed safely."""


@dataclass(frozen=True)
class RefundLedgerBridgeResult:
    recorded: bool
    duplicate: bool
    refund_id: str
    correlation_id: str
    ledger_path: str
    idempotency_path: str
    ledger_line_count: int


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def record_refund_in_ledger(
    ledger_path: Union[str, Path],
    idempotency_path: Union[str, Path],
    event: RefundEvent,
) -> RefundLedgerBridgeResult:
    ledger_p = Path(ledger_path)
    idem_p = Path(idempotency_path)

    refund_id = str(event.refund_id).strip()
    order_id = str(event.order_id).strip()

    if refund_id == "":
        raise RefundLedgerBridgeError("empty_refund_id")
    if order_id == "":
        raise RefundLedgerBridgeError("empty_order_id")

    idem = IdempotencyStore.open(idem_p)
    idem_key = f"refund:{refund_id}"
    correlation_id = f"refund:{refund_id}"

    if idem.has(idem_key):
        return RefundLedgerBridgeResult(
            recorded=False,
            duplicate=True,
            refund_id=refund_id,
            correlation_id=correlation_id,
            ledger_path=str(ledger_p),
            idempotency_path=str(idem_p),
            ledger_line_count=_count_lines(ledger_p),
        )

    ledger = Ledger.open(ledger_p)
    payload = {
        "refund_id": refund_id,
        "order_id": order_id,
        "amount_mxn": str(event.amount),
        "currency": str(event.currency),
        "reason": str(event.reason),
        "created_at": str(event.created_at),
        "line_items": list(event.line_items),
        "source": str(event.source),
    }

    ledger.append(
        event_type="SHOPIFY_REFUND_RECORDED",
        correlation_id=correlation_id,
        idempotency_key=idem_key,
        severity="WARNING",
        payload=payload,
        critical=False,
    )
    idem.put(idem_key, correlation_id)

    return RefundLedgerBridgeResult(
        recorded=True,
        duplicate=False,
        refund_id=refund_id,
        correlation_id=correlation_id,
        ledger_path=str(ledger_p),
        idempotency_path=str(idem_p),
        ledger_line_count=_count_lines(ledger_p),
    )