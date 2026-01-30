import argparse, csv, os, re, sys

PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)

def is_placeholder(url: str) -> bool:
    if not url:
        return False
    return bool(PLACEHOLDER_RE.search(url.strip()))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical-csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max", type=int, default=0, help="0 = sin límite")
    args = ap.parse_args()

    if not os.path.exists(args.canonical_csv):
        print(f"Missing canonical CSV: {args.canonical_csv}", file=sys.stderr)
        return 2

    rows = list(csv.DictReader(open(args.canonical_csv, encoding="utf-8", newline="")))
    out_rows = []
    missing = 0
    placeholder = 0

    for r in rows:
        pid = (r.get("product_id") or "").strip()
        title = (r.get("title") or "").strip()
        img = (r.get("image_url") or "").strip()

        issue = ""
        if not img:
            issue = "missing_image"
            missing += 1
        elif is_placeholder(img):
            issue = "placeholder_image"
            placeholder += 1

        if issue:
            out_rows.append({
                "product_id": pid,
                "title": title,
                "image_url": img,
                "issue": issue
            })

    if args.max and len(out_rows) > args.max:
        out_rows = out_rows[:args.max]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["product_id","title","image_url","issue"])
        w.writeheader()
        w.writerows(out_rows)

    print("image_backlog: OK")
    print(f"- canonical_rows: {len(rows)}")
    print(f"- backlog_rows:   {len(out_rows)}")
    print(f"- missing_image:  {missing}")
    print(f"- placeholder:    {placeholder}")
    print(f"- out:            {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
