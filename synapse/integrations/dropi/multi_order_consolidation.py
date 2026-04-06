# V3GAP:G-02_multi_order_consolidation

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _order_external_id(order: Dict[str, Any]) -> str:
    return str(order.get("id") or order.get("order_id") or "").strip()


def _customer_email(order: Dict[str, Any]) -> str:
    customer = order.get("customer") or {}
    return _normalize_text(customer.get("email") or order.get("email") or "")


def _address_signature(order: Dict[str, Any]) -> Tuple[str, ...]:
    ship = order.get("shipping_address") or {}
    return (
        _normalize_text(ship.get("name")),
        _normalize_text(ship.get("address1")),
        _normalize_text(ship.get("address2")),
        _normalize_text(ship.get("city")),
        _normalize_text(ship.get("zip")),
        _normalize_text(ship.get("country")),
        _normalize_text(ship.get("province")),
    )


def _currency(order: Dict[str, Any]) -> str:
    return str(order.get("currency") or "MXN").strip().upper()


def _coerce_price(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _aggregate_items(orders: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[Tuple[str, str, float], Dict[str, Any]] = {}

    for order in orders:
        for item in (order.get("line_items") or []):
            sku = str(item.get("sku") or item.get("variant_id") or item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            price = _coerce_price(item.get("price"))
            quantity = int(item.get("quantity") or 0)

            key = (sku, title, price)
            if key not in bucket:
                bucket[key] = {
                    "sku": sku,
                    "title": title,
                    "quantity": 0,
                    "price": price,
                }

            bucket[key]["quantity"] += quantity

    return list(bucket.values())


def build_multi_order_consolidation_contract(
    orders,
    *,
    channel: str = "internal",
    metadata=None,
):
    """
    Build the minimal operational contract for consolidating compatible
    Shopify-like orders into a single consolidated order before Dropi forward.
    """
    if not isinstance(orders, list):
        raise TypeError("orders must be list")

    if len(orders) < 2:
        return None

    if not all(isinstance(order, dict) for order in orders):
        raise TypeError("every order must be dict")

    source_order_ids = [_order_external_id(order) for order in orders]
    if not all(source_order_ids):
        return None

    currencies = {_currency(order) for order in orders}
    if len(currencies) != 1:
        return None

    customer_emails = {_customer_email(order) for order in orders}
    if len(customer_emails) != 1 or "" in customer_emails:
        return None

    address_signatures = {_address_signature(order) for order in orders}
    if len(address_signatures) != 1 or all(part == "" for part in next(iter(address_signatures))):
        return None

    first = orders[0]
    consolidated_items = _aggregate_items(orders)
    total_price = sum(_coerce_price(order.get("total_price")) for order in orders)

    consolidated_order = {
        "order_id": "multi:" + ",".join(source_order_ids),
        "currency": _currency(first),
        "email": (first.get("customer") or {}).get("email") or first.get("email") or "",
        "customer": dict(first.get("customer") or {}),
        "shipping_address": dict(first.get("shipping_address") or {}),
        "line_items": consolidated_items,
        "total_price": f"{total_price:.2f}",
        "source_order_ids": source_order_ids,
        "consolidated": True,
    }

    contract = {
        "gate_id": "G-02_multi_order_consolidation",
        "channel": channel,
        "reason": "consolidate_compatible_orders_before_dropi_forward",
        "consolidation_status": "ready_to_forward_consolidated_order",
        "source_order_ids": source_order_ids,
        "order_count": len(source_order_ids),
        "consolidated_order": consolidated_order,
    }

    if metadata is not None:
        contract["metadata"] = dict(metadata)

    return contract
