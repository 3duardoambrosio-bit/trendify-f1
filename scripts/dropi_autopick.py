from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    # "1,234.56" / "$123.45" / "123,45"
    s = re.sub(r"[^\d\.,\-]", "", s)
    if not s:
        return None
    # prefer dot decimal; if only comma exists, treat comma as decimal
    if s.count(",") >= 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    # if both exist, drop commas as thousands
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


def _has_images(it: dict[str, Any]) -> bool:
    v = _get_first(it, ("images", "image_urls", "gallery", "media", "photos"))
    if isinstance(v, list) and len(v) > 0:
        return True
    v2 = _get_first(it, ("image", "image_url", "thumbnail", "thumb", "main_image"))
    return bool(v2)


def _get_text_blob(it: dict[str, Any]) -> str:
    parts = []
    for k in ("title", "name", "product_name", "description", "desc", "body", "category", "tags", "keywords", "brand"):
        v = it.get(k)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            parts.append(" ".join(str(x) for x in v))
        else:
            parts.append(str(v))
    return " ".join(parts).lower()


def _pid(it: dict[str, Any]) -> str:
    for k in ("product_id", "id", "sku", "productId", "productID"):
        v = it.get(k)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return ""


@dataclass(frozen=True)
class Scored:
    product_id: str
    score: float
    reason: dict[str, float]
    title: str


def _score_item(it: dict[str, Any]) -> Scored | None:
    pid = _pid(it)
    if not pid:
        return None

    title = str(_get_first(it, ("title", "name", "product_name", "productName")) or pid).strip()

    rating = _to_float(_get_first(it, ("rating", "stars", "score", "avg_rating")))
    reviews = _to_int(_get_first(it, ("reviews", "reviews_count", "review_count", "ratings_count", "sold", "sales")))

    price = _to_float(_get_first(it, ("price", "sale_price", "selling_price", "min_price", "amount")))
    compare_at = _to_float(_get_first(it, ("compare_at_price", "original_price", "regular_price", "msrp")))

    stock = _to_int(_get_first(it, ("stock", "inventory", "qty", "quantity")))
    ship_days = _to_float(_get_first(it, ("shipping_days", "delivery_days", "ship_days", "delivery_time")))

    has_img = 1.0 if _has_images(it) else 0.0

    # ----- scoring (heurístico, robusto) -----
    # rating: 0..5 -> 0..1
    r_score = 0.0
    if rating is not None:
        r = max(0.0, min(5.0, rating))
        r_score = r / 5.0

    # reviews: log scale, cap
    rv_score = 0.0
    if reviews is not None:
        rv_score = min(1.0, math.log1p(max(0, reviews)) / math.log1p(2000))

    # margin proxy: compare_at - price
    m_score = 0.0
    if price is not None and price > 0:
        if compare_at is not None and compare_at > price:
            m = (compare_at - price) / compare_at
            m_score = max(0.0, min(1.0, m))
        else:
            # if we don't have compare_at, we still like mid-range price vs ultra-cheap
            # (cheap often = low quality + returns)
            # 10..60 gives some points, beyond 200 starts to taper
            p = price
            if p <= 0:
                m_score = 0.0
            elif p < 10:
                m_score = 0.15
            elif p < 60:
                m_score = 0.6
            elif p < 200:
                m_score = 0.45
            else:
                m_score = 0.25

    # stock: prefer in-stock
    s_score = 0.0
    if stock is not None:
        s_score = 1.0 if stock > 0 else 0.0

    # shipping: fewer days better (if unknown, neutral)
    sh_score = 0.5
    if ship_days is not None:
        d = max(0.0, ship_days)
        # 0..14 -> 1..0
        sh_score = max(0.0, min(1.0, 1.0 - (d / 14.0)))

    # final weighted score
    # weights tuned for "sellable product" (not just popular)
    reason = {
        "rating": r_score,
        "reviews": rv_score,
        "images": has_img,
        "margin_proxy": m_score,
        "stock": s_score,
        "shipping": sh_score,
    }
    score = (
        0.28 * r_score +
        0.18 * rv_score +
        0.18 * has_img +
        0.18 * m_score +
        0.10 * s_score +
        0.08 * sh_score
    )

    return Scored(product_id=pid, score=score, reason=reason, title=title)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, help="Dropi dump JSON (offline evidence)")
    ap.add_argument("--out", required=True, help="Output shortlist CSV (product_id column)")
    ap.add_argument("--n", type=int, default=20, help="How many products to select")
    ap.add_argument("--niche", default="", help="Optional keyword filter (space separated)")
    args = ap.parse_args(argv)

    dump_path = Path(args.dump)
    out_path = Path(args.out)

    if not dump_path.exists():
        print(f"ERROR: dump not found: {dump_path}", file=sys.stderr)
        return 2

    dump = _load_json(dump_path)
    items = _extract_items(dump)
    if not items:
        print("ERROR: dump has 0 usable items", file=sys.stderr)
        return 3

    niche = (args.niche or "").strip().lower()
    niche_terms = [t for t in re.split(r"\s+", niche) if t] if niche else []

    scored: list[Scored] = []
    for it in items:
        sc = _score_item(it)
        if not sc:
            continue
        if niche_terms:
            blob = _get_text_blob(it)
            if not all(t in blob for t in niche_terms):
                continue
        scored.append(sc)

    if not scored:
        print("ERROR: 0 products after scoring/filtering", file=sys.stderr)
        return 4

    scored.sort(key=lambda x: x.score, reverse=True)

    n = max(1, int(args.n))
    top = scored[:n]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=["product_id"])
        w.writeheader()
        for s in top:
            w.writerow({"product_id": s.product_id})

    # report for observability
    report_path = out_path.with_suffix(".report.json")
    report = {
        "dump": str(dump_path),
        "out": str(out_path),
        "n": n,
        "picked": [
            {
                "product_id": s.product_id,
                "title": s.title,
                "score": round(s.score, 6),
                "reason": {k: round(v, 6) for k, v in s.reason.items()},
            }
            for s in top
        ],
        "total_scored": len(scored),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not out_path.exists() or out_path.stat().st_size < 10:
        print(f"ERROR: wrote nothing to out: {out_path}", file=sys.stderr)
        return 5

    print("dropi_autopick: OK")
    print(f"- out: {out_path}")
    print(f"- report: {report_path}")
    print(f"- picked: {len(top)} of {len(scored)} scored")
    print(f"- top1: {top[0].product_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())