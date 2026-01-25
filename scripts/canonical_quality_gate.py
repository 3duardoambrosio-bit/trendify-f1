from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load(p: Path) -> dict[str, Any]:
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("report must be a JSON object")
    return obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="canonical_products.report.json")
    ap.add_argument("--allow-seed", action="store_true", help="allow seed to have empty fields")
    ap.add_argument("--min-price-rate", type=float, default=0.60)
    ap.add_argument("--min-image-rate", type=float, default=0.60)
    ap.add_argument("--min-desc-rate", type=float, default=0.60)
    args = ap.parse_args(argv)

    rp = Path(args.report)
    if not rp.exists():
        print(f"ERROR: report not found: {rp}", file=sys.stderr)
        return 2

    rep = _load(rp)
    stats = rep.get("stats") or {}
    rates = rep.get("fill_rates") or {}

    total = int(stats.get("total_ids") or 0)
    with_price = int(stats.get("with_price") or 0)
    with_image = int(stats.get("with_image") or 0)
    with_desc = int(stats.get("with_desc") or 0)

    r_price = float(rates.get("with_price") or 0.0)
    r_image = float(rates.get("with_image") or 0.0)
    r_desc = float(rates.get("with_desc") or 0.0)

    # Seed exception: if only 1 product and it is seed (common in early stage)
    # We don't try to "detect" seed in report here; the release script will pass allow-seed
    # and we accept the all-empty scenario only when allow-seed is on.
    if args.allow_seed and total == 1 and with_price == 0 and with_image == 0 and with_desc == 0:
        print("canonical_quality_gate: OK (seed exception)")
        print(f"- total_ids: {total}")
        print(f"- rates: price={r_price} image={r_image} desc={r_desc}")
        return 0

    ok = True
    problems: list[str] = []

    if total <= 0:
        ok = False
        problems.append("total_ids=0")

    if r_price < args.min_price_rate:
        ok = False
        problems.append(f"price_rate={r_price} < {args.min_price_rate}")

    if r_image < args.min_image_rate:
        ok = False
        problems.append(f"image_rate={r_image} < {args.min_image_rate}")

    if r_desc < args.min_desc_rate:
        ok = False
        problems.append(f"desc_rate={r_desc} < {args.min_desc_rate}")

    if ok:
        print("canonical_quality_gate: OK")
        print(f"- total_ids: {total}")
        print(f"- rates: price={r_price} image={r_image} desc={r_desc}")
        return 0

    print("canonical_quality_gate: FAIL", file=sys.stderr)
    print(f"- total_ids: {total}", file=sys.stderr)
    print(f"- rates: price={r_price} image={r_image} desc={r_desc}", file=sys.stderr)
    print(f"- problems: {problems}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Meaning:", file=sys.stderr)
    print("Your Dropi dump evidence is missing core catalog fields (price/image/description).", file=sys.stderr)
    print("Fix input evidence (API/full export) or keep running seed-only until evidence is richer.", file=sys.stderr)
    return 10


if __name__ == "__main__":
    raise SystemExit(main())