"""Idempotency guard backed by SQLite (stdlib, WAL).

execute_once(key, operation):
- missing -> insert PROCESSING, run op, store COMPLETED
- COMPLETED -> return cached (DUPLICATE), DO NOT re-execute
- FAILED -> retry allowed (delete + re-execute)
- PROCESSING -> ConflictError (in flight)

TTL: 24 hours (cleanup on access)
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional, Tuple

import deal

_TTL_HOURS = 24

_SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('PROCESSING','COMPLETED','FAILED')),
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class ConflictError(RuntimeError):
    """Raised when an operation with the same key is already PROCESSING."""
    pass


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    key: str
    status: str  # COMPLETED | FAILED | DUPLICATE
    result: Any
    was_cached: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _cutoff_iso() -> str:
    cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=_TTL_HOURS)
    return cutoff.isoformat()


def _json_dumps(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"))


def _json_loads(s: str) -> Any:
    return json.loads(s)


class IdempotencyGuard:
    """SQLite-backed idempotency for financial operations."""
    @deal.pre(lambda self, db_path="data/idempotency.db": isinstance(db_path, str) and db_path.strip() != "", message="db_path required")
    @deal.post(lambda result: result is None, message="returns None")

    def __init__(self, db_path: str = "data/idempotency.db") -> None:
        self._db_path = db_path
        d = os.path.dirname(db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        c = self._connect()
        c.close()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute(_SCHEMA)
        except sqlite3.Error:
            c.close()
            raise
        return c

    def _clean_expired(self, c: sqlite3.Connection) -> None:
        c.execute("DELETE FROM idempotency WHERE updated_at < ?", (_cutoff_iso(),))

    def _get(self, c: sqlite3.Connection, key: str) -> Optional[Tuple[str, Optional[str]]]:
        row = c.execute(
            "SELECT status, result FROM idempotency WHERE key=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]), (None if row[1] is None else str(row[1]))

    def _delete(self, c: sqlite3.Connection, key: str) -> None:
        c.execute("DELETE FROM idempotency WHERE key=?", (key,))

    def _insert_processing(self, c: sqlite3.Connection, key: str) -> None:
        now = _now_iso()
        c.execute(
            "INSERT INTO idempotency(key,status,result,created_at,updated_at) VALUES (?,?,?,?,?)",
            (key, "PROCESSING", None, now, now),
        )

    def _update(self, c: sqlite3.Connection, key: str, status: str, payload: Optional[str]) -> None:
        now = _now_iso()
        c.execute(
            "UPDATE idempotency SET status=?, result=?, updated_at=? WHERE key=?",
            (status, payload, now, key),
        )

    def _duplicate(self, key: str, payload: str) -> IdempotencyResult:
        try:
            cached = _json_loads(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError("IDEMPOTENCY_BAD_JSON") from exc
        return IdempotencyResult(key=key, status="DUPLICATE", result=cached, was_cached=True)

    def _claim_key(self, key: str) -> Optional[IdempotencyResult]:
        c = self._connect()
        try:
            self._clean_expired(c)
            row = self._get(c, key)
            if row is not None:
                st, payload = row
                if st == "COMPLETED":
                    if payload is None:
                        raise ValueError("IDEMPOTENCY_CORRUPT_RESULT")
                    return self._duplicate(key, payload)
                if st == "PROCESSING":
                    raise ConflictError(f"KEY_IN_FLIGHT:{key}")
                if st == "FAILED":
                    self._delete(c, key)

            try:
                self._insert_processing(c, key)
                return None
            except sqlite3.IntegrityError:
                row2 = self._get(c, key)
                if row2 is None:
                    self._insert_processing(c, key)
                    return None
                st2, payload2 = row2
                if st2 == "PROCESSING":
                    raise ConflictError(f"KEY_IN_FLIGHT:{key}")
                if st2 == "COMPLETED":
                    if payload2 is None:
                        raise ValueError("IDEMPOTENCY_CORRUPT_RESULT")
                    return self._duplicate(key, payload2)
                self._delete(c, key)
                self._insert_processing(c, key)
                return None
        finally:
            c.close()

    def _finalize(self, key: str, ok: bool, payload: Optional[str]) -> None:
        c = self._connect()
        try:
            if ok:
                if payload is None:
                    raise ValueError("IDEMPOTENCY_INTERNAL_NULL_PAYLOAD")
                self._update(c, key, "COMPLETED", payload)
            else:
                # On failure path: best-effort mark FAILED without masking original error.
                try:
                    self._update(c, key, "FAILED", None)
                except sqlite3.Error:
                    return
        finally:
            c.close()

    @deal.pre(
        lambda self, key, operation: isinstance(key, str) and key.strip() != "",
        message="key required",
    )
    @deal.pre(
        lambda self, key, operation: callable(operation),
        message="operation must be callable",
    )
    @deal.post(
        lambda result: isinstance(result, IdempotencyResult),
        message="returns IdempotencyResult",
    )
    def execute_once(self, key: str, operation: Callable[[], Any]) -> IdempotencyResult:
        dup = self._claim_key(key)
        if dup is not None:
            return dup

        ok = False
        result: Any = None
        payload: Optional[str] = None
        try:
            result = operation()
            payload = _json_dumps(result)
            ok = True
        finally:
            self._finalize(key, ok, payload)

        return IdempotencyResult(key=key, status="COMPLETED", result=result, was_cached=False)

    @deal.pre(
        lambda self, key: isinstance(key, str) and key.strip() != "",
        message="key required",
    )
    @deal.post(lambda result: isinstance(result, bool), message="returns bool")
    def is_completed(self, key: str) -> bool:
        c = self._connect()
        try:
            self._clean_expired(c)
            row = self._get(c, key)
            return (row is not None) and (row[0] == "COMPLETED")
        finally:
            c.close()

    @deal.pre(
        lambda self, key: isinstance(key, str) and key.strip() != "",
        message="key required",
    )
    @deal.post(lambda result: result is None, message="returns None")
    def clear(self, key: str) -> None:
        c = self._connect()
        try:
            self._delete(c, key)
        finally:
            c.close()
