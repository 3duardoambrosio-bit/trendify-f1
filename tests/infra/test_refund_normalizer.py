from __future__ import annotations

from decimal import Decimal

import pytest

from synapse.infra.refund_normalizer import (
    RefundEvent,
    RefundNormalizationError,
    normalize_shopify_refund_event,
    refund_event_from_dict,
    refund_event_to_dict,
)


def test_normalize_shopify_refund_event_happy_path():
    payload = {
        "id": 9001,
        "order_id": 5001,
        "created_at": "2026-03-08T10:00:00Z",
        "currency": "MXN",
        "note": "customer_request",
        "transactions": [
            {"kind": "refund", "status": "success", "amount": Decimal("149.90"), "currency": "MXN"}
        ],
        "refund_line_items": [
            {"line_item": {"sku": "SKU-1"}},
            {"line_item": {"sku": "SKU-2"}},
        ],
    }

    ev = normalize_shopify_refund_event(payload)

    assert isinstance(ev, RefundEvent)
    assert ev.refund_id == "9001"
    assert ev.order_id == "5001"
    assert ev.amount == Decimal("149.90")
    assert ev.currency == "MXN"
    assert ev.reason == "customer_request"
    assert ev.line_items == ("SKU-1", "SKU-2")


def test_normalize_shopify_refund_event_missing_order_id_fail_closed():
    payload = {
        "id": 9001,
        "created_at": "2026-03-08T10:00:00Z",
        "transactions": [{"kind": "refund", "status": "success", "amount": Decimal("10.00")}],
    }

    with pytest.raises(RefundNormalizationError):
        normalize_shopify_refund_event(payload)


def test_refund_event_roundtrip_dict():
    payload = {
        "id": 9002,
        "order_id": 5002,
        "created_at": "2026-03-08T10:00:00Z",
        "transactions": [{"kind": "refund", "status": "success", "amount": Decimal("10.00")}],
    }

    ev = normalize_shopify_refund_event(payload)
    d = refund_event_to_dict(ev)
    ev2 = refund_event_from_dict(d)

    assert ev2 == ev
    assert ev2.amount == Decimal("10.00")