import argparse, csv, os, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", required=True, help="canonical CSV input")
    ap.add_argument("--out", required=True, help="canonical CSV output")
    ap.add_argument("--base-url", required=True, help="https://.../folder (sin slash final o con, da igual)")
    ap.add_argument("--images-dir", required=True, help="carpeta local donde están los PNGs")
    ap.add_argument("--id-col", default="product_id")
    ap.add_argument("--force", action="store_true", help="sobrescribe image_url aunque ya exista")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    images_dir = Path(args.images_dir)

    rows = list(csv.DictReader(open(args.canonical, encoding="utf-8", newline="")))
    if not rows:
        print("patch_baseurl: FAIL (canonical vacío)", file=sys.stderr)
        return 2

    filled = 0
    missing_file = 0

    for r in rows:
        pid = str(r.get(args.id_col) or "").strip()
        if not pid:
            continue

        cur = str(r.get("image_url") or "").strip()
        if cur and not args.force:
            continue

        fp = images_dir / f"{pid}.png"
        if not fp.exists():
            missing_file += 1
            continue

        r["image_url"] = f"{base}/{pid}.png"
        filled += 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    print("patch_baseurl: OK")
    print(f"- canonical_in: {args.canonical}")
    print(f"- out:          {args.out}")
    print(f"- base_url:     {base}")
    print(f"- images_dir:   {images_dir}")
    print(f"- filled:       {filled}")
    print(f"- missing_pngs: {missing_file}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
