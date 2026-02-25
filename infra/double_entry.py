"""
Double-entry bookkeeping layer (NDJSON).

Invariant (valid ledger): total_balance() == Decimal("0.00")
Rule: every recorded transaction must be balanced (sum(amounts)==0.00)

- amount: Decimal (NEVER float)
- Positive = debit, Negative = credit
- Append-only ledger; one entry per line
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator
from uuid import uuid4

import deal

_ZERO = Decimal("0.00")
_Q = Decimal("0.01")
_MAX_LINES = 200_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _q(x: Decimal) -> Decimal:
    return x.quantize(_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: str
    transaction_id: str
    account: str
    amount: Decimal
    created_at: str
    memo: str = ""


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    entries: tuple[LedgerEntry, ...]
    created_at: str


class DoubleEntryLedger:
    """Append-only double-entry ledger backed by NDJSON."""

    def __init__(self, path: str = "data/ledger/double_entry.ndjson") -> None:
        self._path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

    @staticmethod
    def _to_obj(e: LedgerEntry) -> dict:
        return {
            "id": e.id,
            "transaction_id": e.transaction_id,
            "account": e.account,
            "amount": str(_q(e.amount)),
            "created_at": e.created_at,
            "memo": e.memo,
        }

    @staticmethod
    def _from_obj(o: dict) -> LedgerEntry:
        return LedgerEntry(
            id=str(o["id"]),
            transaction_id=str(o["transaction_id"]),
            account=str(o["account"]),
            amount=Decimal(str(o["amount"])),
            created_at=str(o["created_at"]),
            memo=str(o.get("memo", "")),
        )

    def _iter_entries(self) -> Iterator[LedgerEntry]:
        if not os.path.exists(self._path):
            return
        n = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                n += 1
                if n > _MAX_LINES:
                    raise ValueError("LEDGER_TOO_LARGE")
                s = line.strip()
                if not s:
                    continue
                try:
                    yield self._from_obj(json.loads(s))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"LEDGER_CORRUPT_LINE_{n}") from exc
    @deal.pre(lambda self, entries: isinstance(entries, list) and len(entries) >= 2, message="entries must be a list (>=2)")
    @deal.pre(lambda self, entries: all(isinstance(e, LedgerEntry) for e in entries), message="entries must be LedgerEntry")
    @deal.pre(lambda self, entries: all(isinstance(e.amount, Decimal) for e in entries), message="amount must be Decimal")
    @deal.pre(lambda self, entries: len({e.transaction_id for e in entries}) == 1, message="single transaction_id required")
    @deal.pre(lambda self, entries: all(e.account.strip() for e in entries), message="account required")
    @deal.pre(lambda self, entries: all(e.created_at.strip() for e in entries), message="created_at required")
    @deal.pre(
        lambda self, entries: sum((_q(e.amount) for e in entries), _ZERO) == _ZERO,
        message="transaction must be balanced: sum(amount)==0.00",
    )
    @deal.post(lambda result: isinstance(result, Transaction))
    def record(self, entries: list[LedgerEntry]) -> Transaction:
        tx_id = entries[0].transaction_id
        created = entries[0].created_at
        with open(self._path, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(self._to_obj(e), sort_keys=True, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return Transaction(id=tx_id, entries=tuple(entries), created_at=created)

    @deal.pre(lambda self, account: isinstance(account, str) and account.strip() != "", message="account required")
    @deal.post(lambda result: isinstance(result, Decimal))
    def balance(self, account: str) -> Decimal:
        total = _ZERO
        for e in self._iter_entries():
            if e.account == account:
                total += _q(e.amount)
        return _q(total)

    @deal.post(lambda result: result == _ZERO)
    def total_balance(self) -> Decimal:
        total = _ZERO
        for e in self._iter_entries():
            total += _q(e.amount)
        total = _q(total)
        if total != _ZERO:
            raise ValueError("LEDGER_UNBALANCED")
        return _ZERO


@deal.post(lambda result: isinstance(result, str) and len(result) == 32, message="tx_id must be 32 hex chars")
def new_transaction_id() -> str:
    return uuid4().hex


@deal.pre(lambda transaction_id, account, amount, memo="", created_at=None: isinstance(transaction_id, str) and transaction_id.strip() != "", message="transaction_id required")
@deal.pre(lambda transaction_id, account, amount, memo="", created_at=None: isinstance(account, str) and account.strip() != "", message="account required")
@deal.pre(lambda transaction_id, account, amount, memo="", created_at=None: amount.__class__.__name__ == "Decimal", message="amount must be Decimal")
@deal.pre(lambda transaction_id, account, amount, memo="", created_at=None: created_at is None or (isinstance(created_at, str) and created_at.strip() != ""), message="created_at must be str if provided")
@deal.post(lambda result: result.__class__.__name__ == "LedgerEntry", message="must return LedgerEntry")
def make_entry(transaction_id: str, account: str, amount: Decimal, memo: str = "", created_at: str | None = None) -> LedgerEntry:
    return LedgerEntry(
        id=uuid4().hex,
        transaction_id=transaction_id,
        account=account,
        amount=amount,
        created_at=created_at or _now_iso(),
        memo=memo,
    )
