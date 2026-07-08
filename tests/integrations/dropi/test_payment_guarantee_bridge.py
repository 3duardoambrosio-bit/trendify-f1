from datetime import datetime, timezone

from synapse.integrations.dropi.payment_guarantee_bridge import (
    build_dropi_payment_guarantee_bridge,
)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 4, day, hour, 0, 0, tzinfo=timezone.utc)


def test_bridge_waits_for_oxxo_payment_before_guarantee_resolution():
    bridge = build_dropi_payment_guarantee_bridge(
        "oxxo",
        order_id="ORD-1",
        issue_type="damaged",
        order_created_at=_dt(1, 10),
    )

    assert bridge["bridge_id"] == "dropi_payment_guarantee_bridge"
    assert bridge["supplier_payment_ready"] is False
    assert bridge["guarantee_case_ready"] is False
    assert bridge["bridge_status"] == "awaiting_supplier_payment_resolution"
    assert bridge["payment_timing_contract"]["timing_status"] == "awaiting_customer_payment"
    assert bridge["guarantee_flow_contract"]["guarantee_status"] == "awaiting_supplier_payment_resolution"


def test_bridge_opens_guarantee_case_for_prepaid_order():
    bridge = build_dropi_payment_guarantee_bridge(
        "card",
        order_id="ORD-2",
        issue_type="missing_item",
        order_created_at=_dt(1, 11),
        metadata={"source": "shopify"},
    )

    assert bridge["supplier_payment_ready"] is True
    assert bridge["guarantee_case_ready"] is True
    assert bridge["bridge_status"] == "guarantee_case_ready"
    assert bridge["payment_timing_contract"]["timing_status"] == "supplier_payment_scheduled"
    assert bridge["guarantee_flow_contract"]["guarantee_status"] == "dropi_guarantee_case_ready"
    assert bridge["metadata"] == {"source": "shopify"}
    assert bridge["payment_timing_contract"]["metadata"] == {"source": "shopify"}
    assert bridge["guarantee_flow_contract"]["metadata"] == {"source": "shopify"}


def test_bridge_opens_guarantee_case_after_oxxo_payment_confirmation():
    bridge = build_dropi_payment_guarantee_bridge(
        "oxxo",
        order_id="ORD-3",
        issue_type="defective",
        order_created_at=_dt(1, 8),
        customer_paid_at=_dt(2, 9),
        supplier_payment_delay_hours=12,
    )

    assert bridge["supplier_payment_ready"] is True
    assert bridge["guarantee_case_ready"] is True
    assert bridge["bridge_status"] == "guarantee_case_ready"
    assert bridge["payment_timing_contract"]["supplier_payment_due_at"] == _dt(2, 21).isoformat()
    assert bridge["guarantee_flow_contract"]["guarantee_status"] == "dropi_guarantee_case_ready"


def test_bridge_returns_unsupported_issue_state_without_breaking_timing():
    bridge = build_dropi_payment_guarantee_bridge(
        "card",
        order_id="ORD-4",
        issue_type="buyer_remorse",
        order_created_at=_dt(1, 12),
    )

    assert bridge["supplier_payment_ready"] is True
    assert bridge["guarantee_case_ready"] is False
    assert bridge["bridge_status"] == "unsupported_issue_type"
    assert bridge["payment_timing_contract"]["timing_status"] == "supplier_payment_scheduled"
    assert bridge["guarantee_flow_contract"] is None


def test_bridge_requires_order_id():
    try:
        build_dropi_payment_guarantee_bridge(
            "card",
            order_id="",
            issue_type="damaged",
            order_created_at=_dt(1, 12),
        )
    except TypeError as exc:
        assert "order_id" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for missing order_id")