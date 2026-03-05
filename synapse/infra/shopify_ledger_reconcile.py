from __future__ import annotations

"""
S18  Shopify  Ledger Reconciliation Guard

Objetivo:
- Detectar drift entre cobros reales (Shopify orders) y registros internos (ledger).
- FAIL-CLOSED: si falta una orden pagada en ledger, o hay mismatch de monto => BLOCK.

Soporta inputs:
- Shopify orders payload: list[dict] o {"orders":[...]}
- Ledger payload:
  - NDJSON (1 JSON por línea) o list[dict] o {"entries":[...]}

Notas:
- Tolerancia por default: 0.50 MXN (para redondeos/fees menores en datasets de prueba)
- Solo considera órdenes "paid" por default (configurable)

__MARKER__ embedded below.
"""

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import deal

__MARKER__ = "SESSION_S18_shopify_ledger_reconcile_2026-03-04"

log = logging.getLogger(__name__)


# 
# Models
# 

@dataclass(frozen=True)
class ReconcileConfig:
    tolerance_mxn: Decimal = Decimal("0.50")
    paid_statuses: Tuple[str, ...] = ("paid", "partially_paid")
    require_shopify_paid_only: bool = True
    block_on_extra_ledger_entries: bool = False  # default warn


@dataclass(frozen=True)
class OrderRow:
    order_id: str
    total_mxn: Decimal
    currency: str
    financial_status: str


@dataclass(frozen=True)
class LedgerRow:
    order_id: str
    amount_mxn: Decimal


@dataclass(frozen=True)
class DriftItem:
    order_id: str
    kind: str  # missing_in_ledger | amount_mismatch | extra_in_ledger | parse_error
    detail: str


@dataclass(frozen=True)
class ReconcileResult:
    ok: bool
    blocked: bool
    missing_count: int
    mismatch_count: int
    extra_count: int
    items: List[DriftItem]


# 
# Helpers
# 

def _dec(x: Any) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, float):
        # fail-closed: floats in-memory are poison
        raise InvalidOperation("float_not_allowed")
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            raise InvalidOperation("empty_string")
        return Decimal(s)
    raise InvalidOperation(f"unsupported_type:{type(x).__name__}")


def _norm_order_id(x: Any) -> str:
    s = str(x).strip()
    return s


def _first(d: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _load_text(path: str) -> str:
    # BOM-safe
    return Path(path).read_text(encoding="utf-8-sig")


def load_json_any(path: str) -> Any:
    # Also Decimal-safe for floats coming from JSON files
    return json.loads(_load_text(path), parse_float=Decimal)


def load_ledger_any(path: str) -> Any:
    p = Path(path)
    txt = _load_text(str(p))
    # NDJSON must return list even if single-line (common in smoke fixtures)
    suf = p.suffix.lower()
    lines = [ln for ln in txt.splitlines() if ln.strip() != ""]
    if suf in (".ndjson", ".jsonl"):
        return [json.loads(ln, parse_float=Decimal) for ln in lines]
    # Heuristic fallback: multi-line payload that is not a JSON array
    if len(lines) >= 2 and not txt.lstrip().startswith("["):
        try:
            return [json.loads(ln, parse_float=Decimal) for ln in lines]
        except Exception:
            pass
    return json.loads(txt, parse_float=Decimal)

# 
# Parsers
# 

def parse_shopify_orders(payload: Any) -> List[OrderRow]:
    if isinstance(payload, dict) and isinstance(payload.get("orders"), list):
        payload = payload["orders"]

    if not isinstance(payload, list):
        raise ValueError("unsupported_shopify_shape")

    rows: List[OrderRow] = []
    for o in payload:
        if not isinstance(o, dict):
            continue

        oid = _first(o, ("id", "order_id", "order_number", "name"))
        if oid is None:
            continue
        order_id = _norm_order_id(oid)
        if order_id == "":
            continue

        currency = str(_first(o, ("currency", "presentment_currency")) or "MXN").strip() or "MXN"
        financial = str(_first(o, ("financial_status", "display_financial_status")) or "").strip().lower()

        total_raw = _first(
            o,
            (
                "current_total_price",
                "total_price",
                "current_total_price_set",
                "total_price_set",
            ),
        )

        # handle *_set shape: {"shop_money":{"amount":"123.45","currency_code":"MXN"}}
        if isinstance(total_raw, dict):
            shop_money = total_raw.get("shop_money") or total_raw.get("presentment_money") or {}
            if isinstance(shop_money, dict):
                amt = shop_money.get("amount")
                cur = shop_money.get("currency_code") or currency
                if amt is not None:
                    total_raw = amt
                    currency = str(cur).strip() or currency

        total = _dec(total_raw)

        rows.append(OrderRow(order_id=order_id, total_mxn=total, currency=currency, financial_status=financial))

    return rows


def parse_ledger_entries(payload: Any) -> List[LedgerRow]:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        payload = payload["entries"]

    if not isinstance(payload, list):
        raise ValueError("unsupported_ledger_shape")

    rows: List[LedgerRow] = []
    for e in payload:
        if not isinstance(e, dict):
            continue

        oid = _first(e, ("order_id", "shopify_order_id", "order", "orderNumber", "order_name"))
        amt = _first(e, ("amount_mxn", "amount", "mxn", "value", "total_mxn", "total"))

        if oid is None or amt is None:
            continue

        order_id = _norm_order_id(oid)
        if order_id == "":
            continue
        amount = _dec(amt)
        rows.append(LedgerRow(order_id=order_id, amount_mxn=amount))

    return rows


# 
# Core reconcile
# 

@deal.pre(lambda shopify_payload, ledger_payload, cfg=None: shopify_payload is not None)
@deal.pre(lambda shopify_payload, ledger_payload, cfg=None: ledger_payload is not None)
@deal.post(lambda r: isinstance(r, ReconcileResult))
def reconcile_shopify_vs_ledger(
    shopify_payload: Any,
    ledger_payload: Any,
    cfg: Optional[ReconcileConfig] = None,
) -> ReconcileResult:
    cfg = cfg or ReconcileConfig()

    items: List[DriftItem] = []

    try:
        orders = parse_shopify_orders(shopify_payload)
        ledger = parse_ledger_entries(ledger_payload)
    except Exception as e:
        return ReconcileResult(
            ok=False,
            blocked=True,
            missing_count=0,
            mismatch_count=0,
            extra_count=0,
            items=[DriftItem(order_id="*", kind="parse_error", detail=f"{type(e).__name__}:{e}")],
        )

    # Only "paid" by default
    considered = []
    for o in orders:
        if cfg.require_shopify_paid_only:
            if o.financial_status in cfg.paid_statuses:
                considered.append(o)
        else:
            considered.append(o)

    shop_map: Dict[str, OrderRow] = {o.order_id: o for o in considered}

    # ledger aggregation per order
    led_sum: Dict[str, Decimal] = {}
    for r in ledger:
        led_sum[r.order_id] = led_sum.get(r.order_id, Decimal("0")) + r.amount_mxn

    missing = 0
    mismatch = 0
    extra = 0

    # Missing/mismatch
    for oid, o in shop_map.items():
        if oid not in led_sum:
            missing += 1
            items.append(DriftItem(order_id=oid, kind="missing_in_ledger", detail="paid_order_not_in_ledger"))
            continue

        diff = (led_sum[oid] - o.total_mxn).copy_abs()
        if diff > cfg.tolerance_mxn:
            mismatch += 1
            items.append(
                DriftItem(
                    order_id=oid,
                    kind="amount_mismatch",
                    detail=f"shopify={o.total_mxn} ledger={led_sum[oid]} diff={diff} tol={cfg.tolerance_mxn}",
                )
            )

    # Extra ledger entries
    for oid in led_sum.keys():
        if oid not in shop_map:
            extra += 1
            items.append(DriftItem(order_id=oid, kind="extra_in_ledger", detail="ledger_has_order_not_in_shopify_paid_set"))

    blocked = (missing > 0) or (mismatch > 0) or (cfg.block_on_extra_ledger_entries and extra > 0)
    ok = not blocked
    return ReconcileResult(ok=ok, blocked=blocked, missing_count=missing, mismatch_count=mismatch, extra_count=extra, items=items)
