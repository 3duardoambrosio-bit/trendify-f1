import argparse
import json
import os
import sys
from typing import Any, Dict, Tuple

EXIT_FAIL = 3

def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def _i(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default

def load_report(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_metrics(rep: Dict[str, Any]) -> Tuple[int, float, float, float, Dict[str, Any]]:
    """
    Soporta:
    - LEGACY:
        stats.total_ids, stats.with_price, stats.with_image, stats.with_desc
        fill_rates.with_price, fill_rates.with_image, fill_rates.with_desc
    - NUEVO:
        counts.total_rows|total_ids, counts.filled_price|with_price, counts.filled_image|with_image, counts.filled_desc|with_desc
        rates.price|with_price, rates.image|with_image, rates.desc|with_desc
        canonical_csv
    Devuelve:
      total, price_rate, image_rate, desc_rate, counts_normalized
    """
    if isinstance(rep.get("stats"), dict) and isinstance(rep.get("fill_rates"), dict):
        stats = rep.get("stats") or {}
        fr = rep.get("fill_rates") or {}
        total = _i(stats.get("total_ids"), default=_i(stats.get("total_rows"), 0))
        pr = _f(fr.get("with_price"), 0.0)
        ir = _f(fr.get("with_image"), 0.0)
        dr = _f(fr.get("with_desc"), 0.0)

        counts = {
            "total_rows": total,
            "filled_price": _i(stats.get("with_price"), 0),
            "filled_image": _i(stats.get("with_image"), 0),
            "filled_desc":  _i(stats.get("with_desc"), 0),
        }
        return total, pr, ir, dr, counts

    counts_in = rep.get("counts") if isinstance(rep.get("counts"), dict) else {}
    rates_in = rep.get("rates") if isinstance(rep.get("rates"), dict) else {}

    total = _i(counts_in.get("total_rows"), default=_i(counts_in.get("total_ids"), default=_i(rep.get("rows"), 0)))

    pr = rates_in.get("price", None)
    ir = rates_in.get("image", None)
    dr = rates_in.get("desc", None)

    if pr is None: pr = rates_in.get("with_price", 0.0)
    if ir is None: ir = rates_in.get("with_image", 0.0)
    if dr is None: dr = rates_in.get("with_desc", 0.0)

    pr = _f(pr, 0.0)
    ir = _f(ir, 0.0)
    dr = _f(dr, 0.0)

    counts = {
        "total_rows": total,
        "filled_price": _i(counts_in.get("filled_price"), default=_i(counts_in.get("with_price"), 0)),
        "filled_image": _i(counts_in.get("filled_image"), default=_i(counts_in.get("with_image"), 0)),
        "filled_desc":  _i(counts_in.get("filled_desc"),  default=_i(counts_in.get("with_desc"), 0)),
    }
    return total, pr, ir, dr, counts

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--min-price", type=float, default=0.6)
    ap.add_argument("--min-image", type=float, default=0.6)
    ap.add_argument("--min-desc",  type=float, default=0.6)
    ap.add_argument("--allow-seed", action="store_true",
                    help="Permite pasar cuando total==1 (seed-only), aunque rates sean 0.0")

    # NUEVO: compat con runner
    ap.add_argument("--mode", choices=["prod", "bootstrap"], default="prod",
                    help="prod = estricto; bootstrap = normalmente se acompaña de --soft-fail")
    ap.add_argument("--soft-fail", action="store_true",
                    help="Si falla el gate, no rompe el pipeline (returncode 0) pero imprime WARN")

    args = ap.parse_args()

    if not os.path.exists(args.report):
        print(f"canonical_quality_gate: FAIL\n- reason: missing_report\n- report: {args.report}")
        return EXIT_FAIL

    rep = load_report(args.report)
    total, price_rate, image_rate, desc_rate, counts = extract_metrics(rep)

    canonical_csv = rep.get("canonical_csv") or rep.get("canonical") or rep.get("canonical_path") or ""

    if args.allow_seed and total == 1:
        print("canonical_quality_gate: OK (seed exception)")
        print(f"- mode: {args.mode}")
        print("- source: canonical_csv")
        print(f"- canonical_csv: {canonical_csv or f'(unknown; report={args.report})'}")
        print(f"- total_ids: {total}")
        print(f"- rates: price={price_rate:.3f} image={image_rate:.3f} desc={desc_rate:.3f}")
        print(f"- counts: {counts}")
        return 0

    problems = []
    if total <= 0:
        problems.append("no_rows")
    if price_rate < args.min_price:
        problems.append(f"price_rate={price_rate} < {args.min_price}")
    if image_rate < args.min_image:
        problems.append(f"image_rate={image_rate} < {args.min_image}")
    if desc_rate < args.min_desc:
        problems.append(f"desc_rate={desc_rate} < {args.min_desc}")

    if problems:
        tag = "WARN (soft-fail)" if args.soft_fail else "FAIL"
        print(f"canonical_quality_gate: {tag}")
        print(f"- mode: {args.mode}")
        print("- source: canonical_csv")
        print(f"- canonical_csv: {canonical_csv or f'(unknown; report={args.report})'}")
        print(f"- total_ids: {total}")
        print(f"- rates: price={price_rate:.3f} image={image_rate:.3f} desc={desc_rate:.3f}")
        print(f"- counts: {counts}")
        print(f"- problems: {problems}")
        print("")
        print("Meaning:")
        print("Your canonical evidence is missing core catalog fields (price/image/description) at acceptable rates.")
        print("Fix input evidence (API/full export) or run bootstrap mode until evidence is richer.")
        return 0 if args.soft_fail else EXIT_FAIL

    print("canonical_quality_gate: OK")
    print(f"- mode: {args.mode}")
    print("- source: canonical_csv")
    print(f"- canonical_csv: {canonical_csv or f'(unknown; report={args.report})'}")
    print(f"- total_ids: {total}")
    print(f"- rates: price={price_rate:.3f} image={image_rate:.3f} desc={desc_rate:.3f}")
    print(f"- counts: {counts}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
