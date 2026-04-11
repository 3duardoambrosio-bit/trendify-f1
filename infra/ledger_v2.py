from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

import deal

from synapse.infra.time_utc import build_clock_stamp

APPEND_ONLY_DOCUMENT_TYPE = "append-only"
AMENDMENT_DOCUMENT_TYPE = "amendment"
INGEST_TIME_FIELD = "ingest_time"
EVENT_TIME_FIELD = "event_time"

DUMP_SEPARATORS = (",", ":")



def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=DUMP_SEPARATORS, ensure_ascii=False)


def compute_checksum(value: Any) -> str:
    raw = _canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonicalize_money(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        raw = value
    elif isinstance(value, int):
        raw = Decimal(value)
    else:
        raw = Decimal(str(value))
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    event_id: str
    document_type: str
    payload_checksum: str
    payload: Dict[str, Any]
    base_event_id: Optional[str] = None
    ingest_time: str = ""
    event_time: str = ""
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "document_type": self.document_type,
            "payload_checksum": self.payload_checksum,
            "payload": self.payload,
            "base_event_id": self.base_event_id,
            "ingest_time": self.ingest_time,
            "event_time": self.event_time,
            "metadata": self.metadata or {},
        }


@dataclass(frozen=True, slots=True)
class LedgerRecordWriteV2:
    record: LedgerRecord
    status: str
    clock_source_id: str
    clock_unreliable: bool
    clock_skew_estimate: float

    def to_dict(self) -> Dict[str, Any]:
        base = self.record.to_dict()
        base.update(
            {
                "status": self.status,
                "clock_source_id": self.clock_source_id,
                "clock_unreliable": self.clock_unreliable,
                "clock_skew_estimate": self.clock_skew_estimate,
            }
        )
        return base


def build_ledger_record(
    *,
    event_id: str,
    document_type: str,
    payload: Dict[str, Any],
    base_event_id: Optional[str] = None,
    ingest_time: Optional[str] = None,
    event_time: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> LedgerRecord:
    payload_checksum = compute_checksum(payload)
    stamp = build_clock_stamp(event_time=event_time)
    return LedgerRecord(
        event_id=event_id,
        document_type=document_type,
        payload_checksum=payload_checksum,
        payload=payload,
        base_event_id=base_event_id,
        ingest_time=ingest_time or stamp.ingest_time,
        event_time=event_time or stamp.event_time,
        metadata=metadata or {},
    )


def wrap_as_append_only(
    record: LedgerRecord,
    *,
    clock_source_id: str,
    clock_unreliable: bool,
    clock_skew_estimate: float,
    status: str = "APPENDED",
) -> LedgerRecordWriteV2:
    return LedgerRecordWriteV2(
        record=record,
        status=status,
        clock_source_id=clock_source_id,
        clock_unreliable=clock_unreliable,
        clock_skew_estimate=clock_skew_estimate,
    )


def wrap_as_amendment(
    record: LedgerRecord,
    *,
    clock_source_id: str,
    clock_unreliable: bool,
    clock_skew_estimate: float,
    status: str = "AMENDED",
) -> LedgerRecordWriteV2:
    if not record.base_event_id:
        raise ValueError("amendment must reference base_event_id")
    return LedgerRecordWriteV2(
        record=record,
        status=status,
        clock_source_id=clock_source_id,
        clock_unreliable=clock_unreliable,
        clock_skew_estimate=clock_skew_estimate,
    )


def rebuild_checksums(documents: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rebuilt: List[Dict[str, Any]] = []
    for document in documents:
        copy = dict(document)
        copy["payload_checksum"] = compute_checksum(copy.get("payload", {}))
        rebuilt.append(copy)
    return rebuilt


class LedgerClosedError(RuntimeError):
    pass


class LedgerIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LedgerRow:
    entry_id: str
    kind: str
    amount: str
    memo: str
    meta: Dict[str, Any]
    currency: str
    ts: str
    checksum: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "LedgerRow":
        return LedgerRow(
            entry_id=str(data["entry_id"]),
            kind=str(data["kind"]),
            amount=str(data["amount"]),
            memo=str(data.get("memo", "")),
            meta=dict(data.get("meta", {})),
            currency=str(data.get("currency", "USD")),
            ts=str(data["ts"]),
            checksum=str(data["checksum"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "kind": self.kind,
            "amount": self.amount,
            "memo": self.memo,
            "meta": self.meta,
            "currency": self.currency,
            "ts": self.ts,
            "checksum": self.checksum,
        }


class LedgerV2:
    def __init__(
        self,
        *,
        path: str | Path,
        currency: str = "USD",
        fsync: bool = False,
        max_buffer: int = 1000,
    ) -> None:
        self.path = Path(path)
        self.currency = str(currency)
        self.fsync = bool(fsync)
        self.max_buffer = int(max_buffer)
        self._closed = False
        self._buffer: List[LedgerRow] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _row_payload(kind: str, amount: str, memo: str, meta: Dict[str, Any], currency: str, ts: str) -> Dict[str, Any]:
        return {
            "kind": kind,
            "amount": amount,
            "memo": memo,
            "meta": meta,
            "currency": currency,
            "ts": ts,
        }

    @staticmethod
    def _checksum_for(kind: str, amount: str, memo: str, meta: Dict[str, Any], currency: str, ts: str) -> str:
        payload = LedgerV2._row_payload(kind, amount, memo, meta, currency, ts)
        return compute_checksum(payload)

    @deal.pre(lambda self, kind, amount, memo="", meta=None: not isinstance(amount, float))
    def write(
        self,
        kind: str,
        amount: Any,
        *,
        memo: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        if self._closed:
            raise LedgerClosedError("ledger is closed")

        amount_dec = canonicalize_money(amount)
        amount_str = f"{amount_dec:.2f}"
        memo_str = str(memo)
        meta_dict = dict(meta or {})
        ts = build_clock_stamp().ingest_time
        entry_id = uuid4().hex
        checksum = self._checksum_for(str(kind), amount_str, memo_str, meta_dict, self.currency, ts)

        row = LedgerRow(
            entry_id=entry_id,
            kind=str(kind),
            amount=amount_str,
            memo=memo_str,
            meta=meta_dict,
            currency=self.currency,
            ts=ts,
            checksum=checksum,
        )
        self._buffer.append(row)

        if self.max_buffer > 0 and len(self._buffer) >= self.max_buffer:
            self.flush()

        return entry_id

    def _read_file_rows(self) -> List[LedgerRow]:
        if not self.path.exists():
            return []

        rows: List[LedgerRow] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LedgerIntegrityError(f"invalid json line in ledger: {exc}") from exc

            required = {"entry_id", "kind", "amount", "ts", "checksum"}
            if not required.issubset(data.keys()):
                raise LedgerIntegrityError(f"missing keys in ledger row: required={sorted(required)} got={sorted(data.keys())}")

            row = LedgerRow.from_dict(data)
            expected = self._checksum_for(
                row.kind,
                row.amount,
                row.memo,
                row.meta,
                row.currency,
                row.ts,
            )
            if row.checksum != expected:
                raise LedgerIntegrityError("checksum mismatch")
            rows.append(row)
        return rows

    def flush(self) -> int:
        if self._closed:
            raise LedgerClosedError("ledger is closed")
        if not self._buffer:
            return 0

        self.path.parent.mkdir(parents=True, exist_ok=True)
        count = len(self._buffer)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            for row in self._buffer:
                handle.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")
            handle.flush()
            if self.fsync:
                import os
                os.fsync(handle.fileno())
        self._buffer.clear()
        return count

    def query(self, *, kind: Optional[str] = None, limit: int = 100) -> List[LedgerRow]:
        file_rows = self._read_file_rows()
        rows = file_rows + list(self._buffer)
        if kind is not None:
            rows = [r for r in rows if r.kind == kind]
        if limit < 0:
            return rows
        return rows[:limit]

    def verify_integrity(self) -> bool:
        _ = self._read_file_rows()
        for row in self._buffer:
            expected = self._checksum_for(
                row.kind,
                row.amount,
                row.memo,
                row.meta,
                row.currency,
                row.ts,
            )
            if row.checksum != expected:
                raise LedgerIntegrityError("buffer checksum mismatch")
        return True

    def close(self) -> None:
        if self._closed:
            return
        if self._buffer:
            self.flush()
        self._closed = True


__all__ = [
    "APPEND_ONLY_DOCUMENT_TYPE",
    "AMENDMENT_DOCUMENT_TYPE",
    "INGEST_TIME_FIELD",
    "EVENT_TIME_FIELD",
    "LedgerRecord",
    "LedgerRecordWriteV2",
    "LedgerClosedError",
    "LedgerIntegrityError",
    "LedgerRow",
    "LedgerV2",
    "build_ledger_record",
    "wrap_as_append_only",
    "wrap_as_amendment",
    "rebuild_checksums",
    "compute_checksum",
    "canonicalize_money",
    "iso_utc",
]
