from __future__ import annotations

import json
from decimal import Decimal

import pytest

from synapse.infra.refund_ledger_bridge import RefundLedgerBridgeError, record_refund_in_ledger
from synapse.infra.refund_normalizer import RefundEvent


def _mk_event(*, amount: str = "49.90") -> RefundEvent:
    return RefundEvent(
        refund_id="rf_100",
        order_id="ord_900",
        amount=Decimal(amount),
        currency="MXN",
        reason="customer_request",
        created_at="2026-03-09T00:00:00Z",
        line_items=("SKU-1", "SKU-2"),
        source="webhook",
    )


def test_refund_ledger_bridge_writes_event(tmp_path):
    ledger_path = tmp_path / "refund_ledger.ndjson"
    idem_path = tmp_path / "refund_ledger_idempotency.json"

    result = record_refund_in_ledger(ledger_path, idem_path, _mk_event())

    assert result.recorded is True
    assert result.duplicate is False
    assert result.ledger_line_count == 1

    assert idem_path.exists()
    assert idem_path.read_bytes().startswith(b"SQLite format 3\x00")

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])

    assert row["event_type"] == "SHOPIFY_REFUND_RECORDED"
    assert row["correlation_id"] == "refund:rf_100"
    assert row["idempotency_key"] == "refund:rf_100"
    assert row["payload"]["refund_id"] == "rf_100"
    assert row["payload"]["order_id"] == "ord_900"
    assert row["payload"]["amount_mxn"] == "49.90"
    assert row["payload"]["source"] == "webhook"
    assert row["timestamp_utc"].endswith("Z")
    assert len(row["payload_checksum"]) == 64
    assert len(row["checksum"]) == 64


def test_refund_ledger_bridge_is_idempotent(tmp_path):
    ledger_path = tmp_path / "refund_ledger.ndjson"
    idem_path = tmp_path / "refund_ledger_idempotency.json"
    event = _mk_event()

    r1 = record_refund_in_ledger(ledger_path, idem_path, event)
    r2 = record_refund_in_ledger(ledger_path, idem_path, event)

    assert r1.recorded is True
    assert r2.recorded is False
    assert r2.duplicate is True

    assert idem_path.exists()
    assert idem_path.read_bytes().startswith(b"SQLite format 3\x00")

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_refund_ledger_bridge_rejects_payload_conflict_for_same_refund_id(tmp_path):
    ledger_path = tmp_path / "refund_ledger.ndjson"
    idem_path = tmp_path / "refund_ledger_idempotency.json"

    record_refund_in_ledger(ledger_path, idem_path, _mk_event(amount="49.90"))

    with pytest.raises(RefundLedgerBridgeError, match="idempotency_conflict"):
        record_refund_in_ledger(ledger_path, idem_path, _mk_event(amount="59.90"))

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
