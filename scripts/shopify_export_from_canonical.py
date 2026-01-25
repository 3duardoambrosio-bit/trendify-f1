from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


SEED_FALLBACK_PRICE = "29.99"
SEED_FALLBACK_COMPARE_AT = "49.99"
SEED_FALLBACK_TAG = "seed_placeholder_price"


def _to_list(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v).strip() for v in x if str(v).strip()]
    s = str(x).strip()
    if not s:
        return []
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [str(v).strip() for v in obj if str(v).strip()]
        except Exception:
            pass
    parts = re.split(r"[,\|]\s*", s)
    return [p.strip() for p in parts if p.strip()]


def _pick_row(canonical_csv: Path, product_id: str) -> dict[str, str]:
    if not canonical_csv.exists():
        return {}
    with canonical_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("product_id") or "").strip() == product_id:
                return {k: (v or "").strip() for k, v in row.items()}
    return {}


def _merge_tags(existing: str, add: list[str]) -> str:
    raw = [x.strip() for x in (existing or "").split(",") if x.strip()]
    seen = {x.lower() for x in raw}
    out = raw[:]
    for t in add:
        tt = (t or "").strip()
        if not tt:
            continue
        if tt.lower() not in seen:
            seen.add(tt.lower())
            out.append(tt)
    return ", ".join(out)


def _write_csv_utf8_lf(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit-dir", required=True, help="Kit directory (exports/<product_id>)")
    ap.add_argument("--canonical-csv", required=True, help="canonical_products.csv")
    ap.add_argument("--vendor", default="TrendifyHub")
    ap.add_argument("--status", default="draft")
    args = ap.parse_args(argv)

    kit_dir = Path(args.kit_dir)
    product_id = kit_dir.name

    canonical_csv = Path(args.canonical_csv)
    row = _pick_row(canonical_csv, product_id)

    title = row.get("title") or row.get("name") or product_id
    handle = row.get("handle") or f"{product_id}-product"
    tags_raw = row.get("tags") or ""
    tags = ", ".join(_to_list(tags_raw)) if tags_raw else ""

    # images (first image for Shopify import)
    img = (
        row.get("image_url")
        or row.get("image_src")
        or row.get("image")
        or row.get("thumbnail")
        or ""
    )
    if not img:
        imgs = _to_list(row.get("images") or row.get("image_urls") or "")
        img = imgs[0] if imgs else ""

    # pricing
    price = row.get("price") or row.get("sale_price") or ""
    compare_at = row.get("compare_at_price") or row.get("original_price") or row.get("msrp") or ""

    # seed-only fallback (keeps real products clean)
    used_seed_price = False
    if product_id == "seed" and (not price or price.strip() == ""):
        price = SEED_FALLBACK_PRICE
        if not compare_at:
            compare_at = SEED_FALLBACK_COMPARE_AT
        used_seed_price = True
        tags = _merge_tags(tags, [SEED_FALLBACK_TAG])

    # SEO
    seo_title = row.get("seo_title") or title
    seo_desc = row.get("seo_description") or (row.get("description") or row.get("body") or "")

    fieldnames = [
        "Handle",
        "Title",
        "Body (HTML)",
        "Vendor",
        "Type",
        "Tags",
        "Published",
        "Option1 Name",
        "Option1 Value",
        "Variant SKU",
        "Variant Grams",
        "Variant Inventory Tracker",
        "Variant Inventory Qty",
        "Variant Inventory Policy",
        "Variant Fulfillment Service",
        "Variant Price",
        "Variant Compare At Price",
        "Variant Requires Shipping",
        "Variant Taxable",
        "Variant Barcode",
        "Image Src",
        "Image Position",
        "Image Alt Text",
        "SEO Title",
        "SEO Description",
        "Status",
    ]

    out_csv = kit_dir / "shopify" / "shopify_products.csv"

    base = {
        "Handle": handle,
        "Title": title,
        "Body (HTML)": "",
        "Vendor": (row.get("vendor") or "").strip() or args.vendor,
        "Type": (row.get("type") or row.get("category") or "").strip(),
        "Tags": tags,
        "Published": "FALSE",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Variant SKU": row.get("sku") or "",
        "Variant Grams": row.get("grams") or "",
        "Variant Inventory Tracker": "",
        "Variant Inventory Qty": row.get("inventory_qty") or row.get("stock") or row.get("inventory") or "",
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": price,
        "Variant Compare At Price": compare_at,
        "Variant Requires Shipping": "TRUE",
        "Variant Taxable": "TRUE",
        "Variant Barcode": row.get("barcode") or "",
        "Image Src": img,
        "Image Position": "1" if img else "",
        "Image Alt Text": title if img else "",
        "SEO Title": seo_title,
        "SEO Description": seo_desc,
        "Status": args.status,
    }

    _write_csv_utf8_lf(out_csv, fieldnames, [base])

    print("shopify_export_from_canonical: OK")
    print(f"- csv: {out_csv}")
    print(f"- product_id: {product_id}")
    print(f"- has_image: {bool(img)}")
    print(f"- has_price: {bool(price)}")
    print(f"- seed_price_fallback: {used_seed_price}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())