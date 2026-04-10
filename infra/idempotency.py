from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Optional

STATUS_PROCESSING = "PROCESSING"
STATUS_COMPLETED = "COMPLETED"
STATUS_IN_FLIGHT = "IN_FLIGHT"
STATUS_FAILED = "FAILED"
STATUS_CONFLICT = "CONFLICT"
STATUS_DUPLICATE = "DUPLICATE"

DEFAULT_DB_PATH = Path("runtime/idempotency/idempotency.sqlite3")
DEFAULT_TTL_SECONDS = 600


def _now() -> float:
    return time.time()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_checksum(value: Any) -> str:
    raw = _canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def error_checksum(exc: BaseException) -> str:
    raw = f"{type(exc).__name__}:{exc}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def _connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                payload_checksum TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                ttl_seconds INTEGER NOT NULL,
                response_checksum TEXT,
                response_blob TEXT,
                error_checksum TEXT
            )
            """
        )
        yield conn
    finally:
        conn.close()


def _get_row(conn: sqlite3.Connection, key: str) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT * FROM idempotency_keys WHERE key = ?",
        (key,),
    ).fetchone()


def _encode_response(value: Any) -> Optional[str]:
    if value is None:
        return None
    return _canonical_json(value)


def _decode_response(value: Optional[str]) -> Any:
    if not value:
        return None
    return json.loads(value)


def read_state(key: str, *, db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    with _connect(db_path) as conn:
        row = _get_row(conn, key)

    if row is None:
        return {"status": "MISSING", "key": key}

    return {
        "status": row["status"],
        "key": row["key"],
        "payload_checksum": row["payload_checksum"],
        "response_checksum": row["response_checksum"],
        "response": _decode_response(row["response_blob"]),
        "error_checksum": row["error_checksum"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "ttl_seconds": row["ttl_seconds"],
    }


def execute_once(
    key: str,
    payload: Any,
    operation: Callable[[Any], Any],
    *,
    db_path: Path = DEFAULT_DB_PATH,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Dict[str, Any]:
    checksum = payload_checksum(payload)
    now = _now()

    with _connect(db_path) as conn:
        row = _get_row(conn, key)

        if row is None:
            conn.execute(
                """
                INSERT INTO idempotency_keys (
                    key, payload_checksum, status, created_at, updated_at, ttl_seconds
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, checksum, STATUS_PROCESSING, now, now, ttl_seconds),
            )
            conn.commit()
        else:
            if row["payload_checksum"] != checksum:
                return {
                    "status": STATUS_CONFLICT,
                    "key": key,
                    "payload_checksum": checksum,
                    "existing_payload_checksum": row["payload_checksum"],
                }

            status = row["status"]

            if status == STATUS_COMPLETED:
                return {
                    "status": STATUS_DUPLICATE,
                    "key": key,
                    "response_checksum": row["response_checksum"],
                    "response": _decode_response(row["response_blob"]),
                }

            if status == STATUS_PROCESSING:
                return {
                    "status": STATUS_IN_FLIGHT,
                    "key": key,
                }

            if status == STATUS_FAILED:
                conn.execute(
                    """
                    UPDATE idempotency_keys
                    SET status = ?, updated_at = ?, ttl_seconds = ?
                    WHERE key = ?
                    """,
                    (STATUS_PROCESSING, _now(), ttl_seconds, key),
                )
                conn.commit()

    try:
        result = operation(payload)
    except Exception as exc:
        err = error_checksum(exc)
        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE idempotency_keys
                SET status = ?, updated_at = ?, response_checksum = NULL,
                    response_blob = NULL, error_checksum = ?
                WHERE key = ?
                """,
                (STATUS_FAILED, _now(), err, key),
            )
            conn.commit()
        raise

    encoded = _encode_response(result)
    response_ck = payload_checksum(result)

    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE idempotency_keys
            SET status = ?, updated_at = ?, response_checksum = ?,
                response_blob = ?, error_checksum = NULL
            WHERE key = ?
            """,
            (STATUS_COMPLETED, _now(), response_ck, encoded, key),
        )
        conn.commit()

    return {
        "status": STATUS_COMPLETED,
        "key": key,
        "response_checksum": response_ck,
        "response": result,
    }
