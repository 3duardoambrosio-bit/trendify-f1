import argparse, csv, json, os, re, sys

PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def as_candidates(obj):
    # soporta: {"candidates":[...]}, {"items":[...]}, o lista directa
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("candidates", "items", "rows", "data"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
    return []

def pick(d, *keys, default=""):
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v).strip()
        if s:
            return s
    return default

def norm_tags(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return "|".join([str(x).strip() for x in v if str(x).strip()])
    return str(v).strip()

def is_placeholder(url: str) -> bool:
    if not url:
        return False
    return bool(PLACEHOLDER_RE.search(url.strip()))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--mode", choices=["prod", "bootstrap"], default="prod",
                    help="prod = estricto; bootstrap = deja pasar evidencia chafa pero reporta")
    ap.add_argument("--treat-placeholder-as-missing", action="store_true",
                    help="Si se activa, image_url placeholder cuenta como vacío (missing). En prod se fuerza ON.")
    args = ap.parse_args()

    if not os.path.exists(args.shortlist):
        print(f"Missing shortlist: {args.shortlist}", file=sys.stderr)
        return 2
    if not os.path.exists(args.dump):
        print(f"Missing dump: {args.dump}", file=sys.stderr)
        return 2

    dump = load_json(args.dump)
    cands = as_candidates(dump)

    # index por product_id
    m = {}
    for c in cands:
        if not isinstance(c, dict):
            continue
        pid = pick(c, "product_id", "ProductId", "id", default="").strip()
        if pid:
            m[pid] = c

    # leer shortlist
    srows = list(csv.DictReader(open(args.shortlist, encoding="utf-8", newline="")))
    ids = []
    for r in srows:
        pid = (r.get("product_id") or r.get("ProductId") or r.get("id") or "").strip()
        if pid:
            ids.append(pid)

    out_rows = []

    filled_price = 0
    filled_desc  = 0

    # imágenes: raw vs effective (placeholder cuenta o no)
    filled_image_raw = 0
    filled_image_effective = 0
    placeholder_images = 0
    missing_images = 0

    treat_ph_as_missing = bool(args.treat_placeholder_as_missing) or (args.mode == "prod")

    for pid in ids:
        c = m.get(pid, {})
        src = c.get("source") if isinstance(c, dict) else {}
        if not isinstance(src, dict):
            src = {}

        title = pick(src, "title", default="") or pick(c, "title", default="")
        desc  = pick(src, "description", "body_html", "body", default="") or pick(c, "description", default="")
        price = pick(src, "price", default="") or pick(c, "price", default="")
        cap   = pick(src, "compare_at_price", "compare_at", default="") or pick(c, "compare_at_price", default="")
        img   = pick(src, "image_url", "image", "image_src", default="") or pick(c, "image_url", default="")
        tags  = norm_tags(src.get("tags")) or norm_tags(c.get("tags"))

        if price:
            filled_price += 1
        if desc:
            filled_desc += 1

        if img:
            filled_image_raw += 1
            if is_placeholder(img):
                placeholder_images += 1
                if treat_ph_as_missing:
                    img = ""  # lo convertimos a missing real (para prod o cuando se pide)
            if img:
                filled_image_effective += 1
            else:
                missing_images += 1
        else:
            missing_images += 1

        out_rows.append({
            "product_id": pid,
            "title": title,
            "description": desc,
            "price": price,
            "compare_at_price": cap,
            "image_url": img,
            "tags": tags,
        })

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["product_id","title","description","price","compare_at_price","image_url","tags"])
        w.writeheader()
        w.writerows(out_rows)

    report_path = args.report or (args.out.replace(".csv", ".report.json"))

    total = len(out_rows)
    rep = {
        "canonical_csv": args.out,
        "rows": total,
        "filled_price": filled_price,
        "filled_image_raw": filled_image_raw,
        "filled_image_effective": filled_image_effective,
        "filled_desc":  filled_desc,
        "placeholder_images": placeholder_images,
        "missing_images": missing_images,
        "rates": {
            "price": (filled_price / total) if total else 0.0,
            "image_raw": (filled_image_raw / total) if total else 0.0,
            "image": (filled_image_effective / total) if total else 0.0,  # <- el que debe importar
            "desc":  (filled_desc  / total) if total else 0.0,
        },
        "counts": {
            "total_rows": total,
            "filled_price": filled_price,
            "filled_image_raw": filled_image_raw,
            "filled_image": filled_image_effective,   # compat con quality gate
            "filled_desc":  filled_desc,
            "placeholder_images": placeholder_images,
            "missing_images": missing_images,
        },
        "sources": {
            "shortlist": args.shortlist,
            "dump": args.dump,
        },
        "mode": args.mode,
        "treat_placeholder_as_missing": treat_ph_as_missing,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print("build_canonical_from_dropi_v3: OK")
    print(f"- out: {args.out}")
    print(f"- rows: {total}")
    print(f"- report: {report_path}")
    print(f"- fill_price: {filled_price}/{total}")
    print(f"- fill_image_raw: {filled_image_raw}/{total}")
    print(f"- fill_image_effective: {filled_image_effective}/{total}")
    print(f"- placeholders: {placeholder_images}")
    print(f"- mode: {args.mode}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
