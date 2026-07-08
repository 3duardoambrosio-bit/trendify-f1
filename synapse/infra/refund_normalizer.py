from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional, Tuple


class RefundNormalizationError(ValueError):
    """Raised when a refund payload cannot be normalized safely."""


@dataclass(frozen=True)
class RefundEvent:
    refund_id: str
    order_id: str
    amount: Decimal
    currency: str
    reason: str
    created_at: str
    line_items: Tuple[str, ...]
    source: str = "webhook"


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise RefundNormalizationError("invalid_decimal_bool")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise RefundNormalizationError("float_not_allowed")
    s = str(value).strip()
    if s == "":
        raise RefundNormalizationError("empty_decimal")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as e:
        raise RefundNormalizationError("invalid_decimal") from e


def _first(d: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return None


def _extract_amount(payload: Dict[str, Any]) -> Decimal:
    txs = payload.get("transactions")
    if isinstance(txs, list):
        total = Decimal("0")
        used = False
        for tx in txs:
            if not isinstance(tx, dict):
                continue
            kind = str(tx.get("kind") or "").strip().lower()
            parent_kind = str(tx.get("parent_kind") or "").strip().lower()
            status = str(tx.get("status") or "").strip().lower()
            if kind not in ("refund", "suggested_refund") and parent_kind != "refund":
                continue
            if status not in ("", "success", "pending"):
                continue
            raw = _first(tx, ("amount", "maximum_refundable", "processed_amount"))
            if raw is None:
                continue
            amt = _dec(raw)
            if amt < 0:
                amt = -amt
            total += amt
            used = True
        if used and total > 0:
            return total

    raw_amount = _first(payload, ("amount", "total_refunded", "refund_amount"))
    if raw_amount is not None:
        amt = _dec(raw_amount)
        if amt > 0:
            return amt

    subtotal = Decimal("0")
    used = False
    for item in payload.get("refund_line_items") or []:
        if not isinstance(item, dict):
            continue

        raw = _first(item, ("subtotal", "total", "price"))
        if isinstance(raw, dict):
            money = raw.get("shop_money") or raw.get("presentment_money") or {}
            if isinstance(money, dict):
                raw = money.get("amount")

        if raw is None:
            line = item.get("line_item")
            if isinstance(line, dict):
                raw = _first(line, ("price",))

        if raw is None:
            continue

        amt = _dec(raw)
        if amt < 0:
            amt = -amt
        subtotal += amt
        used = True

    if used and subtotal > 0:
        return subtotal

    raise RefundNormalizationError("missing_amount")


def _extract_currency(payload: Dict[str, Any]) -> str:
    cur = _first(payload, ("currency", "order_currency"))
    if cur:
        return str(cur).strip().upper()

    txs = payload.get("transactions")
    if isinstance(txs, list):
        for tx in txs:
            if isinstance(tx, dict):
                cur = _first(tx, ("currency", "currency_code"))
                if cur:
                    return str(cur).strip().upper()

    return "MXN"


def _extract_reason(payload: Dict[str, Any]) -> str:
    note = str(_first(payload, ("note", "reason")) or "").strip().lower()
    if note in ("customer_request", "customer request"):
        return "customer_request"
    if note in ("defective", "damaged", "broken"):
        return "defective"
    if note in ("not_delivered", "not delivered", "lost"):
        return "not_delivered"
    return "other"


def _extract_line_items(payload: Dict[str, Any]) -> Tuple[str, ...]:
    out = []
    for item in payload.get("refund_line_items") or []:
        if not isinstance(item, dict):
            continue

        line = item.get("line_item")
        sku = None
        if isinstance(line, dict):
            sku = line.get("sku") or line.get("vendor_sku") or line.get("id")

        if sku is None:
            sku = item.get("sku") or item.get("line_item_id")

        if sku is not None:
            s = str(sku).strip()
            if s:
                out.append(s)

    return tuple(out)


def normalize_shopify_refund_event(payload: Dict[str, Any], source: str = "webhook") -> RefundEvent:
    if not isinstance(payload, dict):
        raise RefundNormalizationError("payload_not_dict")

    refund_id_raw = _first(payload, ("id", "refund_id"))
    order_id_raw = _first(payload, ("order_id",))
    created_at_raw = _first(payload, ("created_at", "processed_at"))

    if refund_id_raw is None:
        raise RefundNormalizationError("missing_refund_id")
    if order_id_raw is None:
        raise RefundNormalizationError("missing_order_id")
    if created_at_raw is None:
        raise RefundNormalizationError("missing_created_at")

    amount = _extract_amount(payload)
    if amount <= 0:
        raise RefundNormalizationError("non_positive_amount")

    return RefundEvent(
        refund_id=str(refund_id_raw).strip(),
        order_id=str(order_id_raw).strip(),
        amount=amount,
        currency=_extract_currency(payload),
        reason=_extract_reason(payload),
        created_at=str(created_at_raw).strip(),
        line_items=_extract_line_items(payload),
        source=str(source).strip() or "webhook",
    )


def refund_event_to_dict(event: RefundEvent) -> Dict[str, Any]:
    d = asdict(event)
    d["amount"] = str(event.amount)
    d["line_items"] = list(event.line_items)
    return d


def refund_event_from_dict(obj: Dict[str, Any]) -> RefundEvent:
    if not isinstance(obj, dict):
        raise RefundNormalizationError("refund_event_not_dict")

    return RefundEvent(
        refund_id=str(obj["refund_id"]).strip(),
        order_id=str(obj["order_id"]).strip(),
        amount=_dec(obj["amount"]),
        currency=str(obj["currency"]).strip().upper(),
        reason=str(obj["reason"]).strip() or "other",
        created_at=str(obj["created_at"]).strip(),
        line_items=tuple(str(x).strip() for x in (obj.get("line_items") or [])),
        source=str(obj.get("source") or "webhook").strip() or "webhook",
    )