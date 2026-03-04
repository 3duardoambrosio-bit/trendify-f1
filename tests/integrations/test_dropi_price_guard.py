from __future__ import annotations

from decimal import Decimal

import pytest

from synapse.integrations.dropi_price_guard import PriceGuardConfig, evaluate_price_changes


def test_blocks_on_large_increase():
    prev = {"SKU1": "100"}
    curr = {"SKU1": "130"}
    cfg = PriceGuardConfig(max_increase_pct=Decimal("0.20"), min_margin_pct=Decimal("0.10"))
    r = evaluate_price_changes(prev, curr, None, cfg)
    assert r.allowed is False
    assert r.blocked_count == 1
    assert r.items[0].reason == "supplier_increase_over_max_pct"


def test_allows_small_increase():
    prev = {"SKU1": "100"}
    curr = {"SKU1": "110"}
    cfg = PriceGuardConfig(max_increase_pct=Decimal("0.20"), min_margin_pct=Decimal("0.10"))
    r = evaluate_price_changes(prev, curr, None, cfg)
    assert r.allowed is True
    assert r.blocked_count == 0
    assert r.items[0].level == "ok"


def test_margin_floor_blocks_when_sell_provided():
    prev = {"SKU1": "100"}
    curr = {"SKU1": "140"}
    sell = {"SKU1": "150"}  # margin=6.666%
    cfg = PriceGuardConfig(max_increase_pct=Decimal("0.50"), min_margin_pct=Decimal("0.15"))
    r = evaluate_price_changes(prev, curr, sell, cfg)
    assert r.allowed is False
    assert r.blocked_count == 1
    assert r.items[0].reason == "margin_below_floor"


def test_prev_missing_warns_not_blocks():
    prev = {"SKU1": "100"}
    curr = {"SKU2": "50"}
    r = evaluate_price_changes(prev, curr, None, PriceGuardConfig())
    assert r.allowed is True
    assert r.warn_count == 1
    assert r.items[0].reason == "prev_missing_new_sku"


def test_prev_zero_fail_closed():
    prev = {"SKU1": "0"}
    curr = {"SKU1": "10"}
    r = evaluate_price_changes(prev, curr, None, PriceGuardConfig())
    assert r.allowed is False
    assert r.error_count == 1
    assert r.items[0].reason == "invalid_prev_supplier_price"


def test_curr_zero_fail_closed():
    prev = {"SKU1": "10"}
    curr = {"SKU1": "0"}
    r = evaluate_price_changes(prev, curr, None, PriceGuardConfig())
    assert r.allowed is False
    assert r.error_count == 1
    assert r.items[0].reason == "invalid_curr_supplier_price"


def test_float_rejected_fail_closed_parse():
    prev = {"SKU1": 100.0}  # float is forbidden
    curr = {"SKU1": "101"}
    r = evaluate_price_changes(prev, curr, None, PriceGuardConfig())
    assert r.allowed is False
    assert r.error_count == 1
    assert "parse_error" in r.items[0].reason


def test_items_shape_supported():
    prev = {"items": [{"sku": "SKU1", "supplier_price_mxn": "100"}]}
    curr = {"items": [{"sku": "SKU1", "supplier_price_mxn": "110"}]}
    r = evaluate_price_changes(prev, curr, None, PriceGuardConfig(max_increase_pct=Decimal("0.20"), min_margin_pct=Decimal("0.10")))
    assert r.allowed is True
    assert len(r.items) == 1
