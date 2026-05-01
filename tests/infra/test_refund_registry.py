from __future__ import annotations

import json
from decimal import Decimal

import pytest

from synapse.infra.refund_normalizer import RefundEvent
from synapse.infra.refund_registry import RefundRegistryError, record_refund_event


def _mk_event(*, amount: str = "25.00") -> RefundEvent:
    return RefundEvent(
        refund_id="rf_1",
        order_id="ord_1",
        amount=Decimal(amount),
        currency="MXN",
        reason="other",
        created_at="2026-03-08T10:00:00Z",
        line_items=("SKU-1",),
        source="webhook",
    )


def test_record_refund_event_is_idempotent(tmp_path):
    p = tmp_path / "refund_registry.ndjson"
    db = tmp_path / "refund_registry_idempotency.sqlite3"

    r1 = record_refund_event(p, _mk_event())
    r2 = record_refund_event(p, _mk_event())

    assert r1.recorded is True
    assert r1.duplicate is False
    assert r1.line_count == 1

    assert r2.recorded is False
    assert r2.duplicate is True
    assert r2.line_count == 1

    assert db.exists()
    assert db.read_bytes().startswith(b"SQLite format 3\x00")

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["refund_id"] == "rf_1"
    assert obj["amount"] == "25.00"


def test_record_refund_event_conflict_for_same_refund_id_different_payload(tmp_path):
    p = tmp_path / "refund_registry.ndjson"

    record_refund_event(p, _mk_event(amount="25.00"))

    with pytest.raises(RefundRegistryError, match="idempotency_conflict"):
        record_refund_event(p, _mk_event(amount="30.00"))

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
