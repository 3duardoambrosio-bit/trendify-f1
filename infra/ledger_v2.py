# infra/ledger_v2.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union
from uuid import uuid4
import json
import os

import deal


MoneyInput = Union[Decimal, int, str]
_Q2 = Decimal("0.01")


class LedgerError(Exception):
    """Base error for LedgerV2."""


class ValidationError(LedgerError):
    """Invalid input to ledger."""


class LedgerClosedError(LedgerError):
    """Operation attempted after close()."""


class LedgerIOError(LedgerError):
    """File I/O failed."""


class LedgerIntegrityError(LedgerError):
    """Ledger file is corrupted or inconsistent."""


@dataclass(frozen=True, slots=True)
class LedgerRow:
    entry_id: str
    ts_utc: str
    kind: str
    amount: str
    currency: str
    memo: str
    meta: Dict[str, str]


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _is_currency(code: str) -> bool:
    return isinstance(code, str) and len(code) == 3 and code.isalpha() and code.upper() == code


def _ensure_kind(kind: str) -> str:
    if not isinstance(kind, str) or not kind:
        raise ValidationError("kind must be non-empty str")
    k = kind.strip().upper()
    if not k.replace("_", "").isalpha():
        raise ValidationError("kind must be A-Z/_ only")
    if len(k) > 24:
        raise ValidationError("kind length must be <= 24")
    return k


def _reject_float(x: Any) -> None:
    if isinstance(x, float):
        raise ValidationError("float forbidden in money-path; use Decimal|int|str")


def _to_decimal(amount: MoneyInput) -> Decimal:
    _reject_float(amount)
    if isinstance(amount, Decimal):
        dec = amount
    elif isinstance(amount, int):
        dec = Decimal(amount)
    elif isinstance(amount, str):
        try:
            dec = Decimal(amount.strip())
        except (ValueError, ArithmeticError) as e:
            raise ValidationError("invalid decimal string") from e
    else:
        raise ValidationError("amount must be Decimal|int|str")
    return dec.quantize(_Q2, rounding=ROUND_HALF_UP)


def _ensure_nonzero(dec: Decimal) -> None:
    if dec == Decimal("0.00"):
        raise ValidationError("amount must be non-zero")


def _ensure_memo(memo: str) -> str:
    if not isinstance(memo, str):
        raise ValidationError("memo must be str")
    if len(memo) > 200:
        raise ValidationError("memo length must be <= 200")
    return memo


def _ensure_meta(meta: Optional[Mapping[str, str]]) -> Dict[str, str]:
    if meta is None:
        return {}
    if not isinstance(meta, Mapping):
        raise ValidationError("meta must be mapping[str,str]")
    out: Dict[str, str] = {}
    for k, v in meta.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValidationError("meta keys/values must be str")
        if len(k) > 50 or len(v) > 200:
            raise ValidationError("meta key<=50 and value<=200")
        out[k] = v
    return out


def _row_to_json_line(row: LedgerRow) -> str:
    payload = {
        "entry_id": row.entry_id,
        "ts_utc": row.ts_utc,
        "kind": row.kind,
        "amount": row.amount,
        "currency": row.currency,
        "memo": row.memo,
        "meta": dict(row.meta),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _parse_row_dict(d: Any) -> LedgerRow:
    if not isinstance(d, dict):
        raise LedgerIntegrityError("row must be dict")
    try:
        entry_id = d["entry_id"]
        ts_utc = d["ts_utc"]
        kind = d["kind"]
        amount = d["amount"]
        currency = d["currency"]
        memo = d.get("memo", "")
        meta = d.get("meta", {})
    except KeyError as e:
        raise LedgerIntegrityError("missing field") from e
    if not isinstance(entry_id, str) or len(entry_id) < 8:
        raise LedgerIntegrityError("invalid entry_id")
    if not isinstance(ts_utc, str) or "T" not in ts_utc:
        raise LedgerIntegrityError("invalid ts_utc")
    k = _ensure_kind(kind)
    if not _is_currency(currency):
        raise LedgerIntegrityError("invalid currency")
    _reject_float(amount)
    dec = _to_decimal(amount if isinstance(amount, str) else str(amount))
    _ensure_nonzero(dec)
    m = _ensure_memo(memo)
    meta_dict = _ensure_meta(meta)
    return LedgerRow(
        entry_id=entry_id,
        ts_utc=ts_utc,
        kind=k,
        amount=str(dec),
        currency=currency,
        memo=m,
        meta=meta_dict,
    )


def _read_existing_rows(path: Path) -> Tuple[LedgerRow, ...]:
    if not path.exists():
        return tuple()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise LedgerIOError("failed to read ledger file") from e
    rows: list[LedgerRow] = []
    for idx, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            raise LedgerIntegrityError(f"invalid json line {idx}") from e
        rows.append(_parse_row_dict(d))
    return tuple(rows)


class LedgerV2:
    @deal.pre(lambda self, path="data/ledger/ledger_v2.jsonl", currency="USD", fsync=False, max_buffer=100: isinstance(max_buffer, int) and max_buffer > 0)
    @deal.pre(lambda self, path="data/ledger/ledger_v2.jsonl", currency="USD", fsync=False, max_buffer=100: _is_currency(currency))
    @deal.post(lambda result: result is None)
    @deal.raises(ValidationError, LedgerIOError, LedgerIntegrityError)
    def __init__(
        self,
        path: Union[str, Path] = "data/ledger/ledger_v2.jsonl",
        currency: str = "USD",
        fsync: bool = False,
        max_buffer: int = 100,
    ) -> None:
        self.currency: str = currency
        self._path: Path = Path(path)
        self._fsync: bool = bool(fsync)
        self._max_buffer: int = int(max_buffer)
        self._closed: bool = False
        self._buffer: list[LedgerRow] = []
        self._rows: list[LedgerRow] = list(_read_existing_rows(self._path))

    def _ensure_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("ledger is closed")

    def _append_row(self, row: LedgerRow) -> None:
        self._rows.append(row)
        self._buffer.append(row)

    def _write_lines(self, lines: Sequence[str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("a", encoding="utf-8", newline="\n") as f:
                for line in lines:
                    f.write(line + "\n")
                f.flush()
                if self._fsync:
                    os.fsync(f.fileno())
        except OSError as e:
            raise LedgerIOError("failed to append ledger lines") from e

    @deal.pre(lambda self, kind, amount, memo="", meta=None: isinstance(kind, str) and len(kind) > 0)
    @deal.pre(lambda self, kind, amount, memo="", meta=None: amount is not None and not isinstance(amount, float))
    @deal.pre(lambda self, kind, amount, memo="", meta=None: isinstance(memo, str) and len(memo) <= 200)
    @deal.post(lambda result: isinstance(result, str) and len(result) >= 8)
    @deal.raises(ValidationError, LedgerClosedError, LedgerIOError)
    def write(
        self,
        kind: str,
        amount: MoneyInput,
        memo: str = "",
        meta: Optional[Mapping[str, str]] = None,
    ) -> str:
        self._ensure_open()
        k = _ensure_kind(kind)
        dec = _to_decimal(amount)
        _ensure_nonzero(dec)
        m = _ensure_memo(memo)
        meta_dict = _ensure_meta(meta)
        eid = uuid4().hex
        row = LedgerRow(
            entry_id=eid,
            ts_utc=_utc_now_iso(),
            kind=k,
            amount=str(dec),
            currency=self.currency,
            memo=m,
            meta=meta_dict,
        )
        self._append_row(row)
        if len(self._buffer) >= self._max_buffer:
            self.flush()
        return eid

    @deal.pre(lambda self: True)
    @deal.post(lambda result: isinstance(result, int) and result >= 0)
    @deal.raises(LedgerClosedError, LedgerIOError)
    def flush(self) -> int:
        self._ensure_open()
        if not self._buffer:
            return 0
        lines = [_row_to_json_line(r) for r in self._buffer]
        self._write_lines(lines)
        n = len(self._buffer)
        self._buffer.clear()
        return n

    @deal.pre(lambda self, kind=None, limit=1000: isinstance(limit, int) and 1 <= limit <= 100000)
    @deal.post(lambda result: isinstance(result, tuple))
    @deal.raises(ValidationError)
    def query(self, kind: Optional[str] = None, limit: int = 1000) -> Tuple[LedgerRow, ...]:
        if kind is None:
            return tuple(self._rows[-limit:])
        k = _ensure_kind(kind)
        out: list[LedgerRow] = []
        for row in reversed(self._rows):
            if row.kind == k:
                out.append(row)
                if len(out) >= limit:
                    break
        out.reverse()
        return tuple(out)

    @deal.pre(lambda self: True)
    @deal.post(lambda result: result is True)
    @deal.raises(LedgerIntegrityError, LedgerIOError)
    def verify_integrity(self) -> bool:
        rows = _read_existing_rows(self._path)
        seen: set[str] = set()
        for r in rows:
            if r.entry_id in seen:
                raise LedgerIntegrityError("duplicate entry_id")
            seen.add(r.entry_id)
            _reject_float(r.amount)
            dec = _to_decimal(r.amount)
            _ensure_nonzero(dec)
        return True

    @deal.pre(lambda self: True)
    @deal.post(lambda result: result is None)
    @deal.raises(LedgerIOError)
    def close(self) -> None:
        if not self._closed:
            if self._buffer:
                self.flush()
            self._closed = True