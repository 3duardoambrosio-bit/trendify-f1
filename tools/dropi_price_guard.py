from __future__ import annotations

import argparse
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from synapse.integrations.dropi_price_guard import PriceGuardConfig, evaluate_price_changes, load_json

log = logging.getLogger("dropi_price_guard")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", required=True, help="Prev snapshot JSON")
    ap.add_argument("--curr", required=True, help="Curr snapshot JSON")
    ap.add_argument("--sell", required=False, help="Optional sell price map JSON (sku->price)")
    ap.add_argument("--max-increase-pct", default="0.20")
    ap.add_argument("--min-margin-pct", default="0.15")
    args = ap.parse_args()

    prev = load_json(args.prev)
    curr = load_json(args.curr)
    sell = load_json(args.sell) if args.sell else None

    cfg = PriceGuardConfig(
        max_increase_pct=Decimal(args.max_increase_pct),
        min_margin_pct=Decimal(args.min_margin_pct),
    )

    r = evaluate_price_changes(prev, curr, sell, cfg)

    if r.allowed:
        log.info("PASS blocked=%s warn=%s err=%s items=%s", r.blocked_count, r.warn_count, r.error_count, len(r.items))
        return 0

    # show top blocked reasons
    blocked = [it for it in r.items if it.blocked]
    top = blocked[:10]
    log.error("FAIL blocked=%s warn=%s err=%s top=%s", r.blocked_count, r.warn_count, r.error_count, [(x.sku, x.reason) for x in top])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
