from __future__ import annotations

from typing import Any, Mapping

from synapse.integrations.dropi.guarantee_flow import (
    build_dropi_guarantee_flow_contract,
)
from synapse.integrations.dropi.payment_timing import (
    build_dropi_payment_timing_contract,
)


def build_dropi_payment_guarantee_bridge(
    payment_method,
    *,
    order_id,
    issue_type,
    order_created_at,
    customer_paid_at=None,
    supplier_payment_delay_hours: int = 24,
    resolution_preference: str = "replacement",
    channel: str = "internal",
    metadata: Mapping[str, Any] | None = None,
):
    """
    Compose the Dropi payment-timing and guarantee-flow contracts into a
    single runtime bridge. This gives the system one place where customer
    payment state and guarantee eligibility are evaluated together.
    """
    if order_id is None or str(order_id).strip() == "":
        raise TypeError("order_id is required")

    timing_contract = build_dropi_payment_timing_contract(
        payment_method,
        order_created_at=order_created_at,
        customer_paid_at=customer_paid_at,
        supplier_payment_delay_hours=supplier_payment_delay_hours,
        channel=channel,
        metadata=metadata,
    )

    supplier_payment_ready = bool(timing_contract["supplier_payment_ready"])

    guarantee_contract = build_dropi_guarantee_flow_contract(
        issue_type,
        order_id=str(order_id),
        supplier_payment_ready=supplier_payment_ready,
        resolution_preference=resolution_preference,
        channel=channel,
        metadata=metadata,
    )

    if guarantee_contract is None:
        bridge_status = "unsupported_issue_type"
        guarantee_case_ready = False
    elif guarantee_contract["supplier_payment_ready"] is True:
        bridge_status = "guarantee_case_ready"
        guarantee_case_ready = True
    else:
        bridge_status = "awaiting_supplier_payment_resolution"
        guarantee_case_ready = False

    bridge = {
        "bridge_id": "dropi_payment_guarantee_bridge",
        "channel": channel,
        "order_id": str(order_id),
        "payment_method": str(payment_method).strip().lower(),
        "issue_type": None if issue_type is None else str(issue_type).strip().lower(),
        "supplier_payment_ready": supplier_payment_ready,
        "guarantee_case_ready": guarantee_case_ready,
        "bridge_status": bridge_status,
        "payment_timing_contract": timing_contract,
        "guarantee_flow_contract": guarantee_contract,
    }

    if metadata is not None:
        bridge["metadata"] = dict(metadata)

    return bridge