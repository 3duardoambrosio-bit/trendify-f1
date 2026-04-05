# V3GAP:G-01_order_status_auto_reply

def build_order_status_auto_reply_contract(
    order_status,
    *,
    channel: str = "whatsapp",
    order_id=None,
    metadata=None,
):
    """
    Build the lightweight operational contract for sending a customer-facing
    auto-reply when an order reaches a supported status milestone.
    """
    if order_status is None:
        raise TypeError("order_status is required")

    normalized = str(order_status).strip().lower()

    aliases = {
        "paid": "paid",
        "confirmed": "confirmed",
        "processing": "processing",
        "shipped": "shipped",
        "fulfilled": "shipped",
        "in_transit": "shipped",
        "delivered": "delivered",
        "cancelled": "cancelled",
        "canceled": "cancelled",
    }

    if normalized not in aliases:
        return None

    canonical = aliases[normalized]

    contract = {
        "gate_id": "G-01_order_status_auto_reply",
        "channel": channel,
        "reason": "notify_customer_of_order_status",
        "order_status": canonical,
        "reply_template": f"order_status_{canonical}",
        "auto_reply": True,
    }

    if order_id is not None:
        contract["order_id"] = str(order_id)

    if metadata is not None:
        contract["metadata"] = dict(metadata)

    return contract
