import argparse, csv, json, os, sys, re

PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)

def is_placeholder(u: str) -> bool:
    return bool(u) and bool(PLACEHOLDER_RE.search(u.strip()))

def load_dump(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_catalog_map(catalog_csv: str, id_col="product_id", img_col="image_url"):
    m = {}
    with open(catalog_csv, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            pid = (row.get(id_col) or "").strip()
            img = (row.get(img_col) or "").strip()
            if pid:
                m[pid] = img
    return m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--id-col", default="product_id")
    ap.add_argument("--img-col", default="image_url")
    ap.add_argument("--allow-placeholders", action="store_true")
    ap.add_argument("--force", action="store_true", help="sobrescribe image_url aunque ya exista")
    args = ap.parse_args()

    d = load_dump(args.dump)
    if not isinstance(d, dict) or "candidates" not in d or not isinstance(d["candidates"], list):
        print("enrich_dump: FAIL (dump no tiene $.candidates)", file=sys.stderr)
        return 2

    cat = load_catalog_map(args.catalog, id_col=args.id_col, img_col=args.img_col)
    if not cat:
        print("enrich_dump: FAIL (catalog map vacío)", file=sys.stderr)
        return 2

    total = len(d["candidates"])
    filled = 0
    kept = 0
    skipped_no_catalog = 0
    skipped_placeholder = 0

    for c in d["candidates"]:
        if not isinstance(c, dict):
            continue

        # el producto real vive en c["source"] según tu dump
        src = c.get("source") if isinstance(c.get("source"), dict) else c

        pid = str(src.get(args.id_col) or c.get(args.id_col) or "").strip()
        if not pid:
            skipped_no_catalog += 1
            continue

        cur = str(src.get(args.img_col) or "").strip()
        if cur and not args.force:
            kept += 1
            continue

        img = (cat.get(pid) or "").strip()
        if not img:
            skipped_no_catalog += 1
            continue

        if (not args.allow_placeholders) and is_placeholder(img):
            skipped_placeholder += 1
            continue

        src[args.img_col] = img
        filled += 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print("enrich_dump: OK")
    print(f"- dump_in:   {args.dump}")
    print(f"- catalog:   {args.catalog}")
    print(f"- out:       {args.out}")
    print(f"- candidates:{total}")
    print(f"- filled:    {filled}")
    print(f"- kept:      {kept}")
    print(f"- skipped_no_catalog: {skipped_no_catalog}")
    print(f"- skipped_placeholder: {skipped_placeholder}")
    print(f"- allow_placeholders: {args.allow_placeholders}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
