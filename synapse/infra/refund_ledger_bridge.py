from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Union

from infra.idempotency import execute_once
from synapse.infra.refund_normalizer import RefundEvent


class RefundLedgerBridgeError(RuntimeError):
    """Raised when refund ledger recording cannot be completed safely."""


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


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_json(obj: Any) -> str:
    encoded = json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _append_legacy_compatible_row(ledger_path: Path, row: Dict[str, Any]) -> int:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return _count_lines(ledger_path)


def _build_result(
    *,
    recorded: bool,
    duplicate: bool,
    refund_id: str,
    correlation_id: str,
    ledger_path: Path,
    idempotency_path: Path,
    response: Dict[str, Any] | None,
) -> RefundLedgerBridgeResult:
    response = response or {}
    line_count_raw = response.get("ledger_line_count", _count_lines(ledger_path))
    try:
        line_count = int(line_count_raw)
    except (TypeError, ValueError):
        line_count = _count_lines(ledger_path)

    return RefundLedgerBridgeResult(
        recorded=recorded,
        duplicate=duplicate,
        refund_id=refund_id,
        correlation_id=str(response.get("correlation_id") or correlation_id),
        ledger_path=str(response.get("ledger_path") or ledger_path),
        idempotency_path=str(idempotency_path),
        ledger_line_count=line_count,
    )


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

    idem_key = f"refund:{refund_id}"
    correlation_id = idem_key

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

    idem_p.parent.mkdir(parents=True, exist_ok=True)

    def _operation(_: Dict[str, Any]) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "timestamp_utc": _utc_iso(),
            "event_type": "SHOPIFY_REFUND_RECORDED",
            "correlation_id": correlation_id,
            "idempotency_key": idem_key,
            "severity": "WARNING",
            "critical": False,
            "payload": payload,
        }
        row["payload_checksum"] = _sha256_json(payload)
        row["checksum"] = _sha256_json({k: v for k, v in row.items() if k != "checksum"})

        line_count = _append_legacy_compatible_row(ledger_p, row)
        return {
            "correlation_id": correlation_id,
            "ledger_path": str(ledger_p),
            "ledger_line_count": line_count,
        }

    idem_result = execute_once(
        key=idem_key,
        payload=payload,
        operation=_operation,
        db_path=idem_p,
    )

    status = str(idem_result.get("status") or "").strip().lower()
    response = idem_result.get("response")
    if not isinstance(response, dict):
        response = {}

    if status == "completed":
        return _build_result(
            recorded=True,
            duplicate=False,
            refund_id=refund_id,
            correlation_id=correlation_id,
            ledger_path=ledger_p,
            idempotency_path=idem_p,
            response=response,
        )

    if status == "duplicate":
        return _build_result(
            recorded=False,
            duplicate=True,
            refund_id=refund_id,
            correlation_id=correlation_id,
            ledger_path=ledger_p,
            idempotency_path=idem_p,
            response=response,
        )

    if status == "in_flight":
        raise RefundLedgerBridgeError("idempotency_in_flight")

    if status == "conflict":
        raise RefundLedgerBridgeError("idempotency_conflict")

    raise RefundLedgerBridgeError(f"unexpected_idempotency_status:{status or '<empty>'}")
