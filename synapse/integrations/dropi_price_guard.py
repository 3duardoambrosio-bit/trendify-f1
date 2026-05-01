from __future__ import annotations

"""
Dropi Price Guard  S16 (GAP-03)

Fail-closed detector para cambios de precio del proveedor (Dropi) que pueden destruir margen.

Inputs soportados:
- snapshots como dict sku->price (str/number) o {"items":[{sku, supplier_price_mxn, sell_price_mxn?}, ...]}
- sell_price_map opcional sku->sell_price_mxn

Rules:
- supplier_price <= 0 => ERROR (fail-closed para ese SKU)
- prev missing => WARNING (no bloquea)
- prev <= 0 => ERROR (fail-closed)
- delta_pct = (curr - prev) / prev
  - si delta_pct > max_increase_pct => BLOCK
- si hay sell_price:
  - margin_pct = (sell - curr) / sell
  - si margin_pct < min_margin_pct => BLOCK

__MARKER__ embedded in module constant below.
"""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import deal

__MARKER__ = "SESSION_S16_dropi_price_guard_2026-03-03"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceGuardConfig:
    max_increase_pct: Decimal = Decimal("0.20")   # 20%
    min_margin_pct: Decimal = Decimal("0.15")     # 15%
    fail_closed_on_parse_error: bool = True


@dataclass(frozen=True)
class PriceChangeItem:
    sku: str
    prev_supplier: Optional[Decimal]
    curr_supplier: Optional[Decimal]
    sell_price: Optional[Decimal]
    delta_pct: Optional[Decimal]
    margin_pct: Optional[Decimal]
    blocked: bool
    level: str  # ok/warn/block/error
    reason: str


@dataclass(frozen=True)
class PriceGuardResult:
    allowed: bool
    blocked_count: int
    error_count: int
    warn_count: int
    items: List[PriceChangeItem]


def _to_decimal(x: Any) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, (int,)):
        return Decimal(x)
    if isinstance(x, float):
        # FAIL-CLOSED: floats son veneno; obliga a string/int
        raise InvalidOperation("float_not_allowed")
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            raise InvalidOperation("empty_string")
        return Decimal(s)
    raise InvalidOperation(f"unsupported_type:{type(x).__name__}")


def _parse_snapshot(payload: Any) -> Dict[str, Decimal]:
    """
    Normaliza snapshot a dict sku->supplier_price_mxn
    """
    if isinstance(payload, dict):
        # shape A: direct mapping
        if all(isinstance(k, str) for k in payload.keys()) and "items" not in payload:
            out: Dict[str, Decimal] = {}
            for k, v in payload.items():
                if not isinstance(k, str) or k.strip() == "":
                    continue
                out[k.strip()] = _to_decimal(v)
            return out

        # shape B: {"items":[...]}
        items = payload.get("items")
        if isinstance(items, list):
            out2: Dict[str, Decimal] = {}
            for it in items:
                if not isinstance(it, dict):
                    continue
                sku = str(it.get("sku") or "").strip()
                if sku == "":
                    continue
                out2[sku] = _to_decimal(it.get("supplier_price_mxn"))
            return out2

    if isinstance(payload, list):
        # shape C: list of dicts
        out3: Dict[str, Decimal] = {}
        for it in payload:
            if not isinstance(it, dict):
                continue
            sku = str(it.get("sku") or "").strip()
            if sku == "":
                continue
            out3[sku] = _to_decimal(it.get("supplier_price_mxn"))
        return out3

    raise ValueError("unsupported_snapshot_shape")


def _parse_sell_map(payload: Any) -> Dict[str, Decimal]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        out: Dict[str, Decimal] = {}
        for k, v in payload.items():
            if not isinstance(k, str) or k.strip() == "":
                continue
            out[k.strip()] = _to_decimal(v)
        return out
    raise ValueError("unsupported_sell_map_shape")


def _pct(num: Decimal, den: Decimal) -> Decimal:
    if den == Decimal("0"):
        raise ZeroDivisionError("den_zero")
    return num / den


@deal.pre(lambda prev_snapshot, curr_snapshot, sell_price_map=None, cfg=None: prev_snapshot is not None)
@deal.pre(lambda prev_snapshot, curr_snapshot, sell_price_map=None, cfg=None: curr_snapshot is not None)
@deal.post(lambda result: isinstance(result, PriceGuardResult))
def evaluate_price_changes(
    prev_snapshot: Any,
    curr_snapshot: Any,
    sell_price_map: Any = None,
    cfg: Optional[PriceGuardConfig] = None,
) -> PriceGuardResult:
    cfg = cfg or PriceGuardConfig()

    items: List[PriceChangeItem] = []
    blocked = 0
    warns = 0
    errs = 0

    try:
        prev = _parse_snapshot(prev_snapshot)
        curr = _parse_snapshot(curr_snapshot)
        sell = _parse_sell_map(sell_price_map)
    except Exception as e:
        if cfg.fail_closed_on_parse_error:
            it = PriceChangeItem(
                sku="*",
                prev_supplier=None,
                curr_supplier=None,
                sell_price=None,
                delta_pct=None,
                margin_pct=None,
                blocked=True,
                level="error",
                reason=f"parse_error:{type(e).__name__}:{e}",
            )
            return PriceGuardResult(False, 1, 1, 0, [it])
        return PriceGuardResult(True, 0, 0, 0, [])

    for sku, curr_price in curr.items():
        prev_price = prev.get(sku)
        sell_price = sell.get(sku)

        # validate curr supplier
        if curr_price <= Decimal("0"):
            errs += 1
            blocked += 1
            items.append(
                PriceChangeItem(sku, prev_price, curr_price, sell_price, None, None, True, "error", "invalid_curr_supplier_price")
            )
            continue

        if prev_price is None:
            warns += 1
            items.append(
                PriceChangeItem(sku, None, curr_price, sell_price, None, None, False, "warn", "prev_missing_new_sku")
            )
            continue

        if prev_price <= Decimal("0"):
            errs += 1
            blocked += 1
            items.append(
                PriceChangeItem(sku, prev_price, curr_price, sell_price, None, None, True, "error", "invalid_prev_supplier_price")
            )
            continue

        delta = curr_price - prev_price
        try:
            delta_pct = _pct(delta, prev_price)
        except Exception:
            errs += 1
            blocked += 1
            items.append(
                PriceChangeItem(sku, prev_price, curr_price, sell_price, None, None, True, "error", "delta_pct_calc_failed")
            )
            continue

        # margin check (optional)
        margin_pct: Optional[Decimal] = None
        if sell_price is not None:
            if sell_price <= Decimal("0"):
                errs += 1
                blocked += 1
                items.append(
                    PriceChangeItem(sku, prev_price, curr_price, sell_price, delta_pct, None, True, "error", "invalid_sell_price")
                )
                continue
            margin_pct = _pct((sell_price - curr_price), sell_price)

        # block rules
        if delta_pct > cfg.max_increase_pct:
            blocked += 1
            items.append(
                PriceChangeItem(sku, prev_price, curr_price, sell_price, delta_pct, margin_pct, True, "block", "supplier_increase_over_max_pct")
            )
            continue

        if margin_pct is not None and margin_pct < cfg.min_margin_pct:
            blocked += 1
            items.append(
                PriceChangeItem(sku, prev_price, curr_price, sell_price, delta_pct, margin_pct, True, "block", "margin_below_floor")
            )
            continue

        items.append(
            PriceChangeItem(sku, prev_price, curr_price, sell_price, delta_pct, margin_pct, False, "ok", "ok")
        )

    allowed = (blocked == 0)
    return PriceGuardResult(allowed, blocked, errs, warns, items)


def load_json(path: str) -> Any:
    p = Path(path)
    # PowerShell suele escribir UTF-8 con BOM; y JSON puede traer floats => parse_float=Decimal
    return json.loads(p.read_text(encoding="utf-8-sig"), parse_float=Decimal)
