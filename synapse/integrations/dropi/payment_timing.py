# V3GAP:C-01_dropi_payment_timing

from __future__ import annotations

from datetime import datetime, timedelta


def build_dropi_payment_timing_contract(
    payment_method,
    *,
    order_created_at,
    customer_paid_at=None,
    supplier_payment_delay_hours: int = 24,
    channel: str = "internal",
    metadata=None,
):
    """
    Build the minimal operational timing contract that indicates whether
    a Dropi supplier payment can already be scheduled or must still wait
    for customer payment confirmation.
    """
    if payment_method is None:
        raise TypeError("payment_method is required")
    if not isinstance(order_created_at, datetime):
        raise TypeError("order_created_at must be datetime")
    if customer_paid_at is not None and not isinstance(customer_paid_at, datetime):
        raise TypeError("customer_paid_at must be datetime when provided")

    normalized = str(payment_method).strip().lower()
    aliases = {
        "card": "prepaid",
        "credit_card": "prepaid",
        "debit_card": "prepaid",
        "prepaid": "prepaid",
        "oxxo": "cash_pending",
        "cod": "cash_pending",
        "cash_on_delivery": "cash_pending",
        "contraentrega": "cash_pending",
    }

    canonical = aliases.get(normalized, normalized)

    if canonical == "cash_pending" and customer_paid_at is None:
        contract = {
            "gate_id": "C-01_dropi_payment_timing",
            "channel": channel,
            "reason": "await_customer_payment_before_supplier_payment",
            "payment_method": normalized,
            "timing_status": "awaiting_customer_payment",
            "supplier_payment_ready": False,
            "order_created_at": order_created_at.isoformat(),
        }
        if metadata is not None:
            contract["metadata"] = dict(metadata)
        return contract

    reference_at = customer_paid_at or order_created_at
    due_at = reference_at + timedelta(hours=max(0, int(supplier_payment_delay_hours)))

    contract = {
        "gate_id": "C-01_dropi_payment_timing",
        "channel": channel,
        "reason": "schedule_supplier_payment",
        "payment_method": normalized,
        "timing_status": "supplier_payment_scheduled",
        "supplier_payment_ready": True,
        "payment_reference_at": reference_at.isoformat(),
        "supplier_payment_due_at": due_at.isoformat(),
    }

    if metadata is not None:
        contract["metadata"] = dict(metadata)

    return contract
