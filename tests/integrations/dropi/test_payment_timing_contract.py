from datetime import datetime, timedelta, timezone

from synapse.integrations.dropi.payment_timing import (
    build_dropi_payment_timing_contract,
)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 4, day, hour, 0, 0, tzinfo=timezone.utc)


def test_build_dropi_payment_timing_contract_waits_for_oxxo_payment():
    contract = build_dropi_payment_timing_contract(
        "oxxo",
        order_created_at=_dt(1, 10),
    )

    assert contract["gate_id"] == "C-01_dropi_payment_timing"
    assert contract["timing_status"] == "awaiting_customer_payment"
    assert contract["supplier_payment_ready"] is False
    assert contract["payment_method"] == "oxxo"
    assert "supplier_payment_due_at" not in contract


def test_build_dropi_payment_timing_contract_waits_for_cod_payment():
    contract = build_dropi_payment_timing_contract(
        "cash_on_delivery",
        order_created_at=_dt(1, 11),
    )

    assert contract["timing_status"] == "awaiting_customer_payment"
    assert contract["supplier_payment_ready"] is False
    assert contract["payment_method"] == "cash_on_delivery"


def test_build_dropi_payment_timing_contract_schedules_prepaid_immediately():
    contract = build_dropi_payment_timing_contract(
        "card",
        order_created_at=_dt(1, 12),
        supplier_payment_delay_hours=6,
        metadata={"source": "shopify"},
    )

    assert contract["timing_status"] == "supplier_payment_scheduled"
    assert contract["supplier_payment_ready"] is True
    assert contract["payment_reference_at"] == _dt(1, 12).isoformat()
    assert contract["supplier_payment_due_at"] == (_dt(1, 12) + timedelta(hours=6)).isoformat()
    assert contract["metadata"] == {"source": "shopify"}


def test_build_dropi_payment_timing_contract_schedules_oxxo_after_payment_confirmation():
    contract = build_dropi_payment_timing_contract(
        "oxxo",
        order_created_at=_dt(1, 8),
        customer_paid_at=_dt(2, 9),
        supplier_payment_delay_hours=12,
    )

    assert contract["timing_status"] == "supplier_payment_scheduled"
    assert contract["supplier_payment_ready"] is True
    assert contract["payment_reference_at"] == _dt(2, 9).isoformat()
    assert contract["supplier_payment_due_at"] == (_dt(2, 9) + timedelta(hours=12)).isoformat()


def test_build_dropi_payment_timing_contract_requires_datetime_inputs():
    try:
        build_dropi_payment_timing_contract("oxxo", order_created_at="2026-04-01T10:00:00Z")
    except TypeError as exc:
        assert "order_created_at" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for invalid order_created_at")
