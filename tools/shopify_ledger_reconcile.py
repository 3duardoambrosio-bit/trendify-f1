from __future__ import annotations

"""
Shopify ↔ Ledger Reconciliation CLI — S18 + S18.1 hotfix.

Default: paid orders only (safe). Use --all-statuses to include all.
"""

import argparse
import logging
from decimal import Decimal

from synapse.infra.shopify_ledger_reconcile import (
    ReconcileConfig,
    load_json_any,
    load_ledger_any,
    reconcile_shopify_vs_ledger,
)

log = logging.getLogger("shopify_ledger_reconcile")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", required=True, help="Shopify orders JSON (list or {orders:[...]})")
    ap.add_argument("--ledger", required=True, help="Ledger NDJSON/JSON (list or {entries:[...]})")
    ap.add_argument("--tolerance-mxn", default="0.50")
    ap.add_argument("--all-statuses", action="store_true", default=False,
                    help="Consider ALL orders, not just paid (default: paid only)")
    ap.add_argument("--block-on-extra-ledger", action="store_true", default=False)
    args = ap.parse_args()

    orders = load_json_any(args.orders)
    ledger = load_ledger_any(args.ledger)

    cfg = ReconcileConfig(
        tolerance_mxn=Decimal(args.tolerance_mxn),
        require_shopify_paid_only=not args.all_statuses,
        block_on_extra_ledger_entries=bool(args.block_on_extra_ledger),
    )
    r = reconcile_shopify_vs_ledger(orders, ledger, cfg)

    if r.ok:
        log.info("PASS missing=%s mismatch=%s extra=%s items=%s", r.missing_count, r.mismatch_count, r.extra_count, len(r.items))
        return 0

    top = r.items[:10]
    log.error("FAIL missing=%s mismatch=%s extra=%s top=%s", r.missing_count, r.mismatch_count, r.extra_count, [(x.order_id, x.kind) for x in top])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
