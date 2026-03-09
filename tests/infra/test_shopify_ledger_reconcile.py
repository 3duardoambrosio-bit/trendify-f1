from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from synapse.infra.shopify_ledger_reconcile import (
    ReconcileConfig,
    load_json_any,
    load_ledger_any,
    reconcile_shopify_vs_ledger,
)


def test_pass_when_paid_orders_match_ledger_exact():
    shop = [{"id": 1, "financial_status": "paid", "total_price": "100.00", "currency": "MXN"}]
    led = [{"order_id": "1", "amount_mxn": "100.00"}]
    r = reconcile_shopify_vs_ledger(
        shop,
        led,
        ReconcileConfig(tolerance_mxn=Decimal("0.01"), require_shopify_paid_only=True),
    )
    assert r.ok is True
    assert r.blocked is False
    assert r.missing_count == 0
    assert r.mismatch_count == 0


def test_blocks_missing_paid_order():
    shop = [{"id": 1, "financial_status": "paid", "total_price": "100.00"}]
    led = []
    r = reconcile_shopify_vs_ledger(shop, led, ReconcileConfig(require_shopify_paid_only=True))
    assert r.ok is False
    assert r.blocked is True
    assert r.missing_count == 1


def test_blocks_amount_mismatch_over_tolerance():
    shop = [{"id": 1, "financial_status": "paid", "total_price": "100.00"}]
    led = [{"order_id": "1", "amount_mxn": "97.00"}]
    r = reconcile_shopify_vs_ledger(
        shop,
        led,
        ReconcileConfig(tolerance_mxn=Decimal("0.50"), require_shopify_paid_only=True),
    )
    assert r.ok is False
    assert r.mismatch_count == 1


def test_ignores_unpaid_when_require_paid_only():
    shop = [{"id": 1, "financial_status": "pending", "total_price": "100.00"}]
    led = []
    r = reconcile_shopify_vs_ledger(shop, led, ReconcileConfig(require_shopify_paid_only=True))
    assert r.ok is True
    assert r.blocked is False
    assert r.missing_count == 0


def test_warn_extra_ledger_by_default_not_block():
    shop = [{"id": 1, "financial_status": "paid", "total_price": "100.00"}]
    led = [
        {"order_id": "1", "amount_mxn": "100.00"},
        {"order_id": "999", "amount_mxn": "10.00"},
    ]
    r = reconcile_shopify_vs_ledger(
        shop,
        led,
        ReconcileConfig(require_shopify_paid_only=True, block_on_extra_ledger_entries=False),
    )
    assert r.ok is True
    assert r.extra_count == 1


def test_block_extra_ledger_when_configured():
    shop = [{"id": 1, "financial_status": "paid", "total_price": "100.00"}]
    led = [
        {"order_id": "1", "amount_mxn": "100.00"},
        {"order_id": "999", "amount_mxn": "10.00"},
    ]
    r = reconcile_shopify_vs_ledger(
        shop,
        led,
        ReconcileConfig(require_shopify_paid_only=True, block_on_extra_ledger_entries=True),
    )
    assert r.ok is False
    assert r.extra_count == 1


def test_loaders_are_bom_safe_and_decimal_float_safe(tmp_path: Path):
    bom = b"\xef\xbb\xbf"
    orders = tmp_path / "orders.json"
    ledger = tmp_path / "ledger.ndjson"

    orders.write_bytes(bom + b'[{"id": 1, "financial_status":"paid", "total_price": 149.99, "currency":"MXN"}]')
    ledger.write_bytes(bom + b'{"order_id":"1","amount_mxn":149.99}\n')

    o = load_json_any(str(orders))
    l = load_ledger_any(str(ledger))

    assert isinstance(o[0]["total_price"], Decimal)
    assert isinstance(l[0]["amount_mxn"], Decimal)

    r = reconcile_shopify_vs_ledger(
        o,
        l,
        ReconcileConfig(require_shopify_paid_only=True, tolerance_mxn=Decimal("0.01")),
    )
    assert r.ok is True


def test_pass_when_refund_bridge_entry_offsets_gross_ledger_total():
    shop = [
        {
            "id": 1,
            "financial_status": "paid",
            "current_total_price": "80.00",
            "total_price": "100.00",
            "currency": "MXN",
        }
    ]
    led = [
        {"order_id": "1", "amount_mxn": "100.00"},
        {
            "event_type": "SHOPIFY_REFUND_RECORDED",
            "payload": {
                "refund_id": "rf_1",
                "order_id": "1",
                "amount_mxn": "20.00",
                "currency": "MXN",
            },
        },
    ]

    r = reconcile_shopify_vs_ledger(
        shop,
        led,
        ReconcileConfig(tolerance_mxn=Decimal("0.01"), require_shopify_paid_only=True),
    )

    assert r.ok is True
    assert r.blocked is False
    assert r.missing_count == 0
    assert r.mismatch_count == 0
    assert r.extra_count == 0


def test_blocks_when_refund_aware_net_still_mismatches():
    shop = [
        {
            "id": 1,
            "financial_status": "paid",
            "current_total_price": "70.00",
            "total_price": "100.00",
            "currency": "MXN",
        }
    ]
    led = [
        {"order_id": "1", "amount_mxn": "100.00"},
        {
            "event_type": "SHOPIFY_REFUND_RECORDED",
            "payload": {
                "refund_id": "rf_1",
                "order_id": "1",
                "amount_mxn": "20.00",
                "currency": "MXN",
            },
        },
    ]

    r = reconcile_shopify_vs_ledger(
        shop,
        led,
        ReconcileConfig(tolerance_mxn=Decimal("0.01"), require_shopify_paid_only=True),
    )

    assert r.ok is False
    assert r.blocked is True
    assert r.mismatch_count == 1