# V3GAP:C-03_shipping_time_tracker

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict


def _coerce_float(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_shipping_days(payload: Dict[str, Any]):
    for key in ("delivery_time_days", "shipping_days", "delivery_days", "ship_days", "delivery_time"):
        if key in payload:
            days = _coerce_float(payload.get(key))
            if days is not None:
                return max(0.0, days), key
    return None, None


def build_dropi_shipping_time_tracker_contract(
    payload,
    *,
    observed_at,
    channel: str = "internal",
    metadata=None,
):
    """
    Build the minimal operational contract for tracking shipping ETA from
    Dropi/product-catalog timing signals already present in the system.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be dict")
    if not isinstance(observed_at, datetime):
        raise TypeError("observed_at must be datetime")

    shipping_days, source_key = _extract_shipping_days(payload)

    base_contract = {
        "gate_id": "C-03_shipping_time_tracker",
        "channel": channel,
        "reason": "track_supplier_shipping_eta",
        "observed_at": observed_at.isoformat(),
        "shipping_source_key": source_key,
    }

    product_id = payload.get("product_id")
    if product_id not in (None, ""):
        base_contract["product_id"] = str(product_id)

    if shipping_days is None:
        base_contract["tracking_status"] = "shipping_eta_missing"
        base_contract["shipping_eta_ready"] = False
        if metadata is not None:
            base_contract["metadata"] = dict(metadata)
        return base_contract

    eta_at = observed_at + timedelta(days=shipping_days)

    base_contract["tracking_status"] = "shipping_eta_ready"
    base_contract["shipping_eta_ready"] = True
    base_contract["shipping_days"] = shipping_days
    base_contract["shipping_eta_at"] = eta_at.isoformat()

    if metadata is not None:
        base_contract["metadata"] = dict(metadata)

    return base_contract
