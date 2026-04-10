from __future__ import annotations

from typing import Any

from infra.idempotency import (
    STATUS_COMPLETED,
    STATUS_CONFLICT,
    STATUS_DUPLICATE,
    STATUS_FAILED,
    execute_once,
    payload_checksum,
    read_state,
)


def _db_path(tmp_path):
    return tmp_path / "idempotency.sqlite3"


def test_execute_once_completes_and_duplicates(tmp_path):
    db_path = _db_path(tmp_path)
    calls = []

    def op(payload: Any) -> Any:
        calls.append(payload)
        return {"ok": True, "value": payload["value"]}

    payload = {"value": 7}

    first = execute_once("k1", payload, op, db_path=db_path)
    assert first["status"] == STATUS_COMPLETED
    assert len(calls) == 1

    second = execute_once("k1", payload, op, db_path=db_path)
    assert second["status"] == STATUS_DUPLICATE
    assert len(calls) == 1
    assert second["response"] == {"ok": True, "value": 7}


def test_execute_once_conflicts_on_payload_mismatch(tmp_path):
    db_path = _db_path(tmp_path)

    def op(payload: Any) -> Any:
        return {"value": payload["value"]}

    assert execute_once("k1", {"value": 1}, op, db_path=db_path)["status"] == STATUS_COMPLETED

    conflict = execute_once("k1", {"value": 2}, op, db_path=db_path)
    assert conflict["status"] == STATUS_CONFLICT


def test_execute_once_marks_failed_and_allows_recovery(tmp_path):
    db_path = _db_path(tmp_path)

    def failing_op(_payload: Any) -> Any:
        raise RuntimeError("boom")

    try:
        execute_once("k1", {"value": 1}, failing_op, db_path=db_path)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    state = read_state("k1", db_path=db_path)
    assert state["status"] == STATUS_FAILED
    assert state["error_checksum"]

    recovered = execute_once(
        "k1",
        {"value": 1},
        lambda payload: {"ok": True, "value": payload["value"]},
        db_path=db_path,
    )
    assert recovered["status"] == STATUS_COMPLETED


def test_payload_checksum_is_deterministic():
    payload = {"value": "x", "nested": {"a": True, "b": [1, 2, 3]}}
    assert payload_checksum(payload) == payload_checksum(dict(payload))
