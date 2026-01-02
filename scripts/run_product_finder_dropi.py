from __future__ import annotations

import argparse
from decimal import Decimal

from ops.dropi_product_finder import FinderArgs, run

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--max-products", type=int, default=5000)
    ap.add_argument("--categories", type=str, default="")
    ap.add_argument("--min-images", type=int, default=3)
    ap.add_argument("--min-margin-pct", type=str, default="0.20")
    ap.add_argument("--top-n", type=int, default=5)
    ns = ap.parse_args()

    cats = [c.strip() for c in ns.categories.split(",") if c.strip()] if ns.categories else []
    args = FinderArgs(
        page_size=ns.page_size,
        max_products=ns.max_products,
        categories=cats,
        min_images=ns.min_images,
        min_margin_pct=Decimal(ns.min_margin_pct),
        top_n=ns.top_n,
    )

    out = run(args)

    print(f"Catalog products snapshotted: {out['catalog_count']}")
    print(f"Evidence written: {out['evidence']}")
    print("Top candidates:")
    for i, c in enumerate(out["top"], start=1):
        print(f"{i}. [{c.get('score'):.4f}] {c.get('title')}  |  {c.get('category_name')}  | imgs={c.get('images_count')}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
