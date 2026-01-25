from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


# -------------------------
# Helpers: load + extract items
# -------------------------
def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_items(dump: Any) -> list[dict[str, Any]]:
    if isinstance(dump, list):
        return [x for x in dump if isinstance(x, dict)]

    if isinstance(dump, dict):
        for k in ("items", "results", "candidates", "data", "products"):
            v = dump.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # sometimes dict of id->obj
        vals = list(dump.values())
        if vals and all(isinstance(v, dict) for v in vals):
            return vals  # type: ignore[return-value]

    return []


def _get_first(it: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in it and it.get(k) is not None:
            return it.get(k)
    return None


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    s = re.sub(r"[^\d\.,\-]", "", s)  # keep digits, comma, dot, minus
    if not s:
        return None
    if s.count(",") >= 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    if s.count(".") >= 1 and s.count(",") >= 1:
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _to_int(x: Any) -> int | None:
    f = _to_float(x)
    if f is None:
        return None
    try:
        return int(round(f))
    except Exception:
        return None


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s\-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "product"


def _coerce_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def _list_first_url(x: Any) -> str:
    # accept list[str] or list[dict{url/src}]
    if not isinstance(x, list) or not x:
        return ""
    for v in x:
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for k in ("url", "src", "image_url", "image", "link"):
                u = v.get(k)
                if isinstance(u, str) and u.strip():
                    return u.strip()
    return ""


def _extract_image(it: dict[str, Any]) -> str:
    # direct single url
    direct = _get_first(it, ("image_src", "image_url", "image", "thumbnail", "thumb", "main_image", "primary_image"))
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    # list-ish
    li = _get_first(it, ("images", "image_urls", "gallery", "media", "photos"))
    u = _list_first_url(li)
    if u:
        return u

    # nested common shapes
    for k in ("assets", "pictures"):
        li2 = it.get(k)
        u2 = _list_first_url(li2)
        if u2:
            return u2

    return ""


def _extract_tags(it: dict[str, Any]) -> str:
    # tags may be string "a,b" or list
    raw = _get_first(it, ("tags", "keywords", "keyword", "category", "categories", "niche", "brand"))
    tags: list[str] = []

    def add(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, list):
            for x in v:
                add(x)
            return
        if isinstance(v, dict):
            # pick meaningful stringy values
            for x in v.values():
                add(x)
            return
        s = str(v).strip()
        if not s:
            return
        parts = re.split(r"[,\|/]\s*|\s{2,}", s)
        for p in parts:
            p = p.strip()
            if p:
                tags.append(p)

    add(raw)
    # de-dup keep order
    out: list[str] = []
    seen: set[str] = set()
    for t in tags:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return ", ".join(out)


def _extract_price(it: dict[str, Any]) -> tuple[str, str]:
    # returns (price, compare_at_price) as strings (Shopify-friendly)
    price = _to_float(_get_first(it, ("price", "sale_price", "selling_price", "min_price", "amount", "current_price")))
    compare_at = _to_float(_get_first(it, ("compare_at_price", "original_price", "regular_price", "msrp", "old_price")))

    # try variants
    variants = _get_first(it, ("variants", "variant", "skus", "offers"))
    if (price is None) and isinstance(variants, list) and variants:
        # pick min positive
        vals = []
        for v in variants:
            if not isinstance(v, dict):
                continue
            pv = _to_float(_get_first(v, ("price", "sale_price", "selling_price", "amount")))
            if pv is not None and pv > 0:
                vals.append(pv)
            cv = _to_float(_get_first(v, ("compare_at_price", "original_price", "regular_price", "msrp")))
            if compare_at is None and cv is not None and cv > 0:
                compare_at = cv
        if vals:
            price = min(vals)

    def fmt(x: float | None) -> str:
        if x is None:
            return ""
        # keep as plain string; Shopify accepts decimals with dot
        return f"{x:.2f}".rstrip("0").rstrip(".")

    return (fmt(price), fmt(compare_at))


def _extract_stock(it: dict[str, Any]) -> str:
    s = _to_int(_get_first(it, ("stock", "inventory", "qty", "quantity", "inventory_qty")))
    if s is None:
        return ""
    return str(max(0, s))


def _extract_sku(it: dict[str, Any]) -> str:
    return _coerce_str(_get_first(it, ("sku", "SKU", "variant_sku", "product_sku", "code")))


def _extract_grams(it: dict[str, Any]) -> str:
    g = _to_int(_get_first(it, ("grams", "weight_grams", "weight_g", "weight")))
    if g is None:
        return ""
    return str(max(0, g))


def _extract_title(it: dict[str, Any], product_id: str) -> str:
    t = _coerce_str(_get_first(it, ("title", "name", "product_name", "productName")))
    return t or product_id


def _extract_desc(it: dict[str, Any]) -> str:
    d = _coerce_str(_get_first(it, ("description", "desc", "body", "body_html", "product_description", "long_description")))
    return d


def _pid(it: dict[str, Any]) -> str:
    for k in ("product_id", "id", "sku", "productId", "productID"):
        v = it.get(k)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return ""


def _read_shortlist(shortlist_csv: Path) -> list[str]:
    with shortlist_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or "product_id" not in r.fieldnames:
            raise ValueError("shortlist.csv must have product_id column")
        ids = []
        for row in r:
            pid = (row.get("product_id") or "").strip()
            if pid:
                ids.append(pid)
        if not ids:
            raise ValueError("shortlist.csv has 0 product_id rows")
        return ids


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    shortlist_csv = Path(args.shortlist)
    dump_json = Path(args.dump)
    out_csv = Path(args.out)

    if not shortlist_csv.exists():
        print(f"ERROR: shortlist not found: {shortlist_csv}", file=sys.stderr)
        return 2
    if not dump_json.exists():
        print(f"ERROR: dump not found: {dump_json}", file=sys.stderr)
        return 3

    ids = _read_shortlist(shortlist_csv)

    dump = _load_json(dump_json)
    items = _extract_items(dump)
    if not items:
        print("ERROR: dump has 0 usable items", file=sys.stderr)
        return 4

    by_id: dict[str, dict[str, Any]] = {}
    for it in items:
        pid = _pid(it)
        if pid:
            by_id[pid] = it

    rows: list[dict[str, str]] = []
    stats = {
        "total_ids": len(ids),
        "found_in_dump": 0,
        "with_price": 0,
        "with_image": 0,
        "with_desc": 0,
    }

    # canonical schema (what downstream expects)
    fieldnames = [
        "product_id",
        "handle",
        "title",
        "description",
        "price",
        "compare_at_price",
        "image_url",
        "tags",
        "sku",
        "grams",
        "inventory_qty",
        "vendor",
        "type",
    ]

    for pid in ids:
        it = by_id.get(pid, {})
        title = _extract_title(it, pid) if it else pid
        handle = _slug(_coerce_str(_get_first(it, ("handle",))) or title) if it else _slug(title)
        desc = _extract_desc(it) if it else ""
        price, compare_at = _extract_price(it) if it else ("", "")
        img = _extract_image(it) if it else ""
        tags = _extract_tags(it) if it else ""

        sku = _extract_sku(it) if it else ""
        grams = _extract_grams(it) if it else ""
        inv = _extract_stock(it) if it else ""

        vendor = _coerce_str(_get_first(it, ("vendor", "brand", "seller"))) if it else ""
        ptype = _coerce_str(_get_first(it, ("type", "category", "product_type"))) if it else ""

        if it:
            stats["found_in_dump"] += 1
        if price:
            stats["with_price"] += 1
        if img:
            stats["with_image"] += 1
        if desc:
            stats["with_desc"] += 1

        rows.append({
            "product_id": pid,
            "handle": handle,
            "title": title,
            "description": desc,
            "price": price,
            "compare_at_price": compare_at,
            "image_url": img,
            "tags": tags,
            "sku": sku,
            "grams": grams,
            "inventory_qty": inv,
            "vendor": vendor,
            "type": ptype,
        })

    _write_csv(out_csv, fieldnames, rows)

    report = out_csv.with_suffix(".report.json")
    report.write_text(json.dumps({
        "shortlist": str(shortlist_csv),
        "dump": str(dump_json),
        "out": str(out_csv),
        "stats": stats,
        "fill_rates": {
            "found_in_dump": round(stats["found_in_dump"] / max(1, stats["total_ids"]), 6),
            "with_price": round(stats["with_price"] / max(1, stats["total_ids"]), 6),
            "with_image": round(stats["with_image"] / max(1, stats["total_ids"]), 6),
            "with_desc": round(stats["with_desc"] / max(1, stats["total_ids"]), 6),
        }
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if not out_csv.exists() or out_csv.stat().st_size < 20:
        print(f"ERROR: wrote nothing to out: {out_csv}", file=sys.stderr)
        return 5

    print("build_canonical_from_dropi_v2: OK")
    print(f"- out: {out_csv}")
    print(f"- rows: {len(rows)}")
    print(f"- report: {report}")
    print(f"- fill_price: {stats['with_price']}/{stats['total_ids']}")
    print(f"- fill_image: {stats['with_image']}/{stats['total_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())