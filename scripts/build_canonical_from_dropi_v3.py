import argparse, csv, json, os, sys

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
    s = str(v).strip()
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default="")
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
        if not pid:
            continue
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
    filled_image = 0
    filled_desc  = 0

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

        if price: filled_price += 1
        if img:   filled_image += 1
        if desc:  filled_desc  += 1

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
    rep = {
        "canonical_csv": args.out,
        "rows": len(out_rows),
        "filled_price": filled_price,
        "filled_image": filled_image,
        "filled_desc":  filled_desc,
        "rates": {
            "price": (filled_price / len(out_rows)) if out_rows else 0.0,
            "image": (filled_image / len(out_rows)) if out_rows else 0.0,
            "desc":  (filled_desc  / len(out_rows)) if out_rows else 0.0,
        },
        "counts": {
            "total_rows": len(out_rows),
            "filled_price": filled_price,
            "filled_image": filled_image,
            "filled_desc":  filled_desc,
        },
        "sources": {
            "shortlist": args.shortlist,
            "dump": args.dump,
        }
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print("build_canonical_from_dropi_v3: OK")
    print(f"- out: {args.out}")
    print(f"- rows: {len(out_rows)}")
    print(f"- report: {report_path}")
    print(f"- fill_price: {filled_price}/{len(out_rows)}")
    print(f"- fill_image: {filled_image}/{len(out_rows)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
