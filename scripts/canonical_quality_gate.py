from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MIN_RATE_DEFAULT = 0.60


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _unique_preserve(xs: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in xs:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _csv_candidate_from_report(report_path: Path) -> Optional[Path]:
    """
    Supports both:
      - canonical_products.csv.report.json  -> canonical_products.csv
      - canonical_products.report.json      -> canonical_products.csv
    """
    name = report_path.name
    if not name.endswith(".report.json"):
        return None

    base = name[: -len(".report.json")]  # may end with .csv or not
    p1 = report_path.with_name(base)  # could be "...csv"
    if p1.exists() and p1.suffix.lower() == ".csv":
        return p1

    p2 = report_path.with_name(base + ".csv")
    if p2.exists():
        return p2

    return None


def _calc_rates_from_canonical_csv(csv_path: Path) -> Tuple[List[str], Dict[str, float], Dict[str, int]]:
    ids: List[str] = []
    total = 0
    filled_price = 0
    filled_image = 0
    filled_desc = 0

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            total += 1

            pid = _safe_str(row.get("product_id"))
            if pid:
                ids.append(pid)

            price = _safe_str(row.get("price"))
            if price:
                filled_price += 1

            image = (
                _safe_str(row.get("image_url"))
                or _safe_str(row.get("image"))
                or _safe_str(row.get("image_src"))
            )
            if image:
                filled_image += 1

            desc = (
                _safe_str(row.get("description"))
                or _safe_str(row.get("body_html"))
                or _safe_str(row.get("Body (HTML)"))
            )
            if desc:
                filled_desc += 1

    if total <= 0:
        rates = {"price": 0.0, "image": 0.0, "desc": 0.0}
    else:
        rates = {
            "price": filled_price / total,
            "image": filled_image / total,
            "desc": filled_desc / total,
        }

    counts = {
        "total_rows": total,
        "filled_price": filled_price,
        "filled_image": filled_image,
        "filled_desc": filled_desc,
    }
    return _unique_preserve(ids), rates, counts


def _parse_ratio(v: Any) -> Tuple[int, int]:
    """
    Accepts:
      - {"filled": 1, "total": 2}
      - [1, 2] / (1, 2)
      - "1/2"
      - {"ok": 1, "n": 2} (best-effort)
    """
    if v is None:
        return (0, 0)

    if isinstance(v, dict):
        for a, b in (("filled", "total"), ("ok", "n"), ("have", "total"), ("hit", "total")):
            if a in v and b in v:
                try:
                    return (int(v[a]), int(v[b]))
                except Exception:
                    return (0, 0)
        return (0, 0)

    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return (int(v[0]), int(v[1]))
        except Exception:
            return (0, 0)

    if isinstance(v, str) and "/" in v:
        parts = v.split("/", 1)
        try:
            return (int(parts[0].strip()), int(parts[1].strip()))
        except Exception:
            return (0, 0)

    return (0, 0)


def _extract_ids_from_report(report: Any) -> List[str]:
    if not isinstance(report, dict):
        return []

    # Common keys
    for k in ("product_ids", "ids"):
        v = report.get(k)
        if isinstance(v, list):
            return _unique_preserve([_safe_str(x) for x in v])

    # Sometimes nested under meta / summary / stats
    for path in (
        ("meta", "product_ids"),
        ("meta", "ids"),
        ("summary", "product_ids"),
        ("summary", "ids"),
        ("stats", "product_ids"),
        ("stats", "ids"),
    ):
        cur: Any = report
        ok = True
        for step in path:
            if not isinstance(cur, dict) or step not in cur:
                ok = False
                break
            cur = cur[step]
        if ok and isinstance(cur, list):
            return _unique_preserve([_safe_str(x) for x in cur])

    # Or infer from rows-like structures
    for k in ("rows", "items", "candidates", "top"):
        v = report.get(k)
        if isinstance(v, list):
            ids = []
            for it in v:
                if isinstance(it, dict):
                    pid = _safe_str(it.get("product_id") or it.get("id"))
                    if pid:
                        ids.append(pid)
            if ids:
                return _unique_preserve(ids)

    return []


def _get_total_ids_from_report(report: Any) -> int:
    if not isinstance(report, dict):
        return 0

    # direct
    for k in ("total_ids", "total", "n"):
        v = report.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)

    stats = report.get("stats")
    if isinstance(stats, dict):
        v = stats.get("total_ids") or stats.get("total") or stats.get("n")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)

    return 0


def _calc_rates_from_report(report: Any) -> Dict[str, float]:
    if not isinstance(report, dict):
        return {"price": 0.0, "image": 0.0, "desc": 0.0}

    # Preferred schema used in tests:
    #   {"fill_rates": {"with_price": 0.0, "with_image": 0.0, "with_desc": 0.0}}
    fr = report.get("fill_rates")
    if isinstance(fr, dict):
        def _f(k: str) -> float:
            v = fr.get(k)
            try:
                return float(v)
            except Exception:
                return 0.0

        return {
            "price": _f("with_price"),
            "image": _f("with_image"),
            "desc": _f("with_desc"),
        }

    # Other possible schema:
    fp = report.get("fill_price")
    fi = report.get("fill_image")
    fd = report.get("fill_desc") or report.get("fill_description")

    filled_p, total_p = _parse_ratio(fp)
    filled_i, total_i = _parse_ratio(fi)
    filled_d, total_d = _parse_ratio(fd)

    def rate(f: int, t: int) -> float:
        if t <= 0:
            return 0.0
        return float(f) / float(t)

    return {
        "price": rate(filled_p, total_p),
        "image": rate(filled_i, total_i),
        "desc": rate(filled_d, total_d),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="Path to canonical_products.report.json (or legacy *.csv.report.json)")
    ap.add_argument("--min-rate", type=float, default=MIN_RATE_DEFAULT, help="Minimum acceptable fill rate per field")
    ap.add_argument("--allow-seed", action="store_true", help="Allow seed-only run even if evidence is thin")
    args = ap.parse_args()

    report_p = Path(args.report)
    if not report_p.exists():
        print(f"canonical_quality_gate: ERROR report not found: {report_p}")
        return 2

    report = _read_json(report_p)

    csv_p = _csv_candidate_from_report(report_p)
    ids: List[str] = []
    rates: Dict[str, float] = {"price": 0.0, "image": 0.0, "desc": 0.0}
    counts: Dict[str, int] = {}

    source = "report"
    if csv_p and csv_p.exists():
        ids, rates, counts = _calc_rates_from_canonical_csv(csv_p)
        source = "canonical_csv"
        total_ids = len(ids)
    else:
        ids = _extract_ids_from_report(report)
        rates = _calc_rates_from_report(report)
        # If report doesn't include ids, fall back to stats.total_ids
        total_ids = len(ids) if ids else _get_total_ids_from_report(report)
        counts = {}

    # Seed exception logic:
    # - Best case: ids == ["seed"]
    # - Test/legacy case: no ids, but total_ids==1 and allow-seed is explicitly set
    seed_only = (len(ids) == 1 and ids[0] == "seed")
    seed_unknown_but_single = (not ids and total_ids == 1)

    if args.allow_seed and (seed_only or seed_unknown_but_single):
        print("canonical_quality_gate: OK (seed exception)")
        print(f"- source: {source}")
        if csv_p:
            print(f"- canonical_csv: {csv_p}")
        print(f"- total_ids: {total_ids}")
        print(f"- rates: price={rates['price']:.3f} image={rates['image']:.3f} desc={rates['desc']:.3f}")
        if counts:
            print(f"- counts: {counts}")
        return 0

    problems: List[str] = []
    if total_ids <= 0:
        problems.append("total_ids=0")
    if rates["price"] < args.min_rate:
        problems.append(f"price_rate={rates['price']:.1f} < {args.min_rate}")
    if rates["image"] < args.min_rate:
        problems.append(f"image_rate={rates['image']:.1f} < {args.min_rate}")
    if rates["desc"] < args.min_rate:
        problems.append(f"desc_rate={rates['desc']:.1f} < {args.min_rate}")

    if problems:
        print("canonical_quality_gate: FAIL")
        print(f"- source: {source}")
        if csv_p:
            print(f"- canonical_csv: {csv_p}")
        print(f"- total_ids: {total_ids}")
        print(f"- rates: price={rates['price']:.3f} image={rates['image']:.3f} desc={rates['desc']:.3f}")
        if counts:
            print(f"- counts: {counts}")
        print(f"- problems: {problems}")
        print("")
        print("Meaning:")
        print("Your canonical evidence is missing core catalog fields (price/image/description) at acceptable rates.")
        print("Fix input evidence (API/full export) or run seed-only until evidence is richer.")
        return 2

    print("canonical_quality_gate: OK")
    print(f"- source: {source}")
    if csv_p:
        print(f"- canonical_csv: {csv_p}")
    print(f"- total_ids: {total_ids}")
    print(f"- rates: price={rates['price']:.3f} image={rates['image']:.3f} desc={rates['desc']:.3f}")
    if counts:
        print(f"- counts: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())