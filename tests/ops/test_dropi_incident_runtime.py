from __future__ import annotations

from datetime import datetime, timezone

from ops.dropi_incident_runtime import DropiIncidentContext, DropiIncidentRuntime


class FakeLedger:
    def __init__(self) -> None:
        self.events = []

    def write(self, kind, amount, *, memo="", meta=None):
        self.events.append(
            {
                "kind": kind,
                "amount": amount,
                "memo": memo,
                "meta": dict(meta or {}),
            }
        )


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 4, day, hour, 0, 0, tzinfo=timezone.utc)


def test_runtime_holds_when_oxxo_not_paid_and_emits_ledger():
    ledger = FakeLedger()
    runtime = DropiIncidentRuntime(ledger=ledger)

    decision = runtime.decide(
        DropiIncidentContext(
            order_id="ORD-1",
            payment_method="oxxo",
            issue_type="damaged",
            order_created_at=_dt(1, 10),
        )
    )

    assert decision.action == "hold"
    assert decision.reason == "awaiting_supplier_payment_resolution"
    assert decision.bridge_status == "awaiting_supplier_payment_resolution"
    assert decision.guarantee_case_ready is False
    assert decision.supplier_payment_ready is False

    assert len(ledger.events) == 1
    event = ledger.events[0]
    assert event["kind"] == "dropi_guarantee_bridge_decided"
    assert event["amount"] == "0.00"
    assert event["memo"] == "dropi_bridge:ORD-1:damaged"
    assert event["meta"]["entity_type"] == "order"
    assert event["meta"]["entity_id"] == "ORD-1"
    assert event["meta"]["action"] == "hold"
    assert event["meta"]["bridge_status"] == "awaiting_supplier_payment_resolution"


def test_runtime_opens_case_for_prepaid_order_and_emits_ledger():
    ledger = FakeLedger()
    runtime = DropiIncidentRuntime(ledger=ledger)

    decision = runtime.decide(
        DropiIncidentContext(
            order_id="ORD-2",
            payment_method="card",
            issue_type="missing_item",
            order_created_at=_dt(1, 11),
            metadata={"source": "shopify"},
        )
    )

    assert decision.action == "open_case"
    assert decision.reason == "ready_for_dropi_case"
    assert decision.bridge_status == "guarantee_case_ready"
    assert decision.guarantee_case_ready is True
    assert decision.supplier_payment_ready is True

    assert len(ledger.events) == 1
    event = ledger.events[0]
    assert event["kind"] == "dropi_guarantee_bridge_decided"
    assert event["amount"] == "0.00"
    assert event["meta"]["action"] == "open_case"
    assert event["meta"]["guarantee_case_ready"] is True
    assert event["meta"]["metadata"] == {"source": "shopify"}


def test_runtime_reviews_unsupported_issue_type():
    ledger = FakeLedger()
    runtime = DropiIncidentRuntime(ledger=ledger)

    decision = runtime.decide(
        DropiIncidentContext(
            order_id="ORD-3",
            payment_method="card",
            issue_type="buyer_remorse",
            order_created_at=_dt(1, 12),
        )
    )

    assert decision.action == "review"
    assert decision.reason == "unsupported_issue_type"
    assert decision.bridge_status == "unsupported_issue_type"
    assert decision.guarantee_case_ready is False
    assert decision.supplier_payment_ready is True

    assert len(ledger.events) == 1
    assert ledger.events[0]["meta"]["action"] == "review"


def test_runtime_raises_for_empty_order_id():
    ledger = FakeLedger()
    runtime = DropiIncidentRuntime(ledger=ledger)

    try:
        runtime.decide(
            DropiIncidentContext(
                order_id="",
                payment_method="card",
                issue_type="damaged",
                order_created_at=_dt(1, 12),
            )
        )
    except TypeError as exc:
        assert "order_id" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for empty order_id")