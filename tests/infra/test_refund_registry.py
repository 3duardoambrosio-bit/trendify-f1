from __future__ import annotations

import json
from decimal import Decimal

from synapse.infra.refund_normalizer import RefundEvent
from synapse.infra.refund_registry import record_refund_event


def test_record_refund_event_is_idempotent(tmp_path):
    p = tmp_path / "refund_registry.ndjson"
    ev = RefundEvent(
        refund_id="rf_1",
        order_id="ord_1",
        amount=Decimal("25.00"),
        currency="MXN",
        reason="other",
        created_at="2026-03-08T10:00:00Z",
        line_items=("SKU-1",),
        source="webhook",
    )

    r1 = record_refund_event(p, ev)
    r2 = record_refund_event(p, ev)

    assert r1.recorded is True
    assert r1.duplicate is False
    assert r1.line_count == 1

    assert r2.recorded is False
    assert r2.duplicate is True
    assert r2.line_count == 1

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["refund_id"] == "rf_1"
    assert obj["amount"] == "25.00"