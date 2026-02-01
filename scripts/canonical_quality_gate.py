import argparse, csv, json, os, re, sys

EXIT_FAIL = 1
PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)

PRICE_COLS = ["price","price_value","price_amount","price_mxn","sale_price","final_price","amount"]
IMAGE_COLS = ["image_url","image","img","image_src","imageUrl","featured_image","main_image"]
DESC_COLS  = ["description","desc","body_html","body","product_description","short_description"]

def is_placeholder(url: str) -> bool:
    if not url:
        return False
    return bool(PLACEHOLDER_RE.search(str(url).strip()))

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def pick_report_canonical(rep: dict) -> str:
    for k in ("canonical_csv","canonical","canonical_path","canonical_products_csv","path"):
        v = rep.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def get_first_present(row: dict, keys: list[str]) -> str:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""

def is_price_ok(s: str) -> bool:
    if not s:
        return False
    s2 = re.sub(r"[^\d\.]", "", s)
    try:
        return float(s2) > 0
    except Exception:
        return False

def is_image_ok(img: str, mode: str, allow_placeholders: bool) -> bool:
    if not img:
        return False
    if img and img.strip().startswith("http") is False:
        # si alguien mete rutas raras, igual lo cuenta como "hay algo" (bootstrap tolerante)
        return True if mode == "bootstrap" else False
    if is_placeholder(img):
        return (mode == "bootstrap" and allow_placeholders)
    return True

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--canonical-csv", help="Ruta directa al canonical_products.csv")
    g.add_argument("--report", help="Ruta al canonical_products.report.json (se extrae canonical_csv)")

    ap.add_argument("--min-price", type=float, default=0.6)
    ap.add_argument("--min-image", type=float, default=0.6)
    ap.add_argument("--min-desc", type=float, default=0.6)
    ap.add_argument("--mode", choices=["prod","bootstrap"], default="prod")
    ap.add_argument("--soft-fail", action="store_true")
    ap.add_argument("--allow-placeholders", action="store_true", help="En bootstrap, cuenta placeholders como imágenes válidas")

    args = ap.parse_args()

    canonical_csv = args.canonical_csv
    if args.report:
        if not os.path.exists(args.report):
            print(f"Missing report: {args.report}", file=sys.stderr)
            return 2
        rep = load_json(args.report)
        canonical_csv = pick_report_canonical(rep)
        if not canonical_csv:
            print("Report does not include canonical_csv", file=sys.stderr)
            return 2

    if not canonical_csv or not os.path.exists(canonical_csv):
        print(f"Missing canonical CSV: {canonical_csv}", file=sys.stderr)
        return 2

    rows = list(csv.DictReader(open(canonical_csv, encoding="utf-8", newline="")))
    total = len(rows)
    counts = {"total_rows": total, "filled_price": 0, "filled_image": 0, "filled_desc": 0, "placeholders_counted": 0}

    for r in rows:
        price = get_first_present(r, PRICE_COLS)
        img   = get_first_present(r, IMAGE_COLS)
        desc  = get_first_present(r, DESC_COLS)

        if is_price_ok(price):
            counts["filled_price"] += 1

        ok_img = is_image_ok(img, mode=args.mode, allow_placeholders=args.allow_placeholders)
        if ok_img:
            counts["filled_image"] += 1
            if is_placeholder(img) and args.mode == "bootstrap" and args.allow_placeholders:
                counts["placeholders_counted"] += 1

        if desc:
            counts["filled_desc"] += 1

    if total == 0:
        price_rate = image_rate = desc_rate = 0.0
    else:
        price_rate = counts["filled_price"] / total
        image_rate = counts["filled_image"] / total
        desc_rate  = counts["filled_desc"]  / total

    problems = []
    if total == 0:
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
        print(f"- allow_placeholders: {args.allow_placeholders}")
        print("- source: canonical_csv")
        print(f"- canonical_csv: {canonical_csv or f'(unknown; report={args.report})'}")
        print(f"- total_ids: {total}")
        print(f"- rates: price={price_rate:.3f} image={image_rate:.3f} desc={desc_rate:.3f}")
        print(f"- counts: {counts}")
        print(f"- problems: {problems}")
        return 0 if args.soft_fail else EXIT_FAIL

    print("canonical_quality_gate: OK")
    print(f"- mode: {args.mode}")
    print(f"- allow_placeholders: {args.allow_placeholders}")
    print("- source: canonical_csv")
    print(f"- canonical_csv: {canonical_csv or f'(unknown; report={args.report})'}")
    print(f"- total_ids: {total}")
    print(f"- rates: price={price_rate:.3f} image={image_rate:.3f} desc={desc_rate:.3f}")
    print(f"- counts: {counts}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
