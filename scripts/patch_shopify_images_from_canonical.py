# scripts/patch_shopify_images_from_canonical.py
import argparse, csv, os, re, sys
from typing import Dict, Tuple, Optional

PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)

def is_placeholder(u: str) -> bool:
    return bool(u) and bool(PLACEHOLDER_RE.search(u.strip()))

def norm(s: str) -> str:
    return (s or "").strip()

def detect_col(fields, preferred_names):
    fset = {c.lower(): c for c in fields}
    for name in preferred_names:
        if name.lower() in fset:
            return fset[name.lower()]
    return None

def detect_image_col(fields):
    # Shopify typical: "Image Src"
    # Other variants: "Image Src 1", "Image URL", "image_url", "image", etc.
    exact = detect_col(fields, ["Image Src", "Image URL", "image_url", "image", "image_src"])
    if exact:
        return exact
    # heuristic: contains both image & src/url
    for c in fields:
        lc = c.lower()
        if "image" in lc and ("src" in lc or "url" in lc):
            return c
    # fallback: any column containing "image"
    for c in fields:
        if "image" in c.lower():
            return c
    return None

def detect_handle_col(fields):
    return detect_col(fields, ["Handle", "handle", "product_handle", "slug"])

def detect_title_col(fields):
    return detect_col(fields, ["Title", "title", "Name", "name"])

def detect_image_position_col(fields):
    return detect_col(fields, ["Image Position", "image_position", "ImagePosition"])

def detect_image_alt_col(fields):
    return detect_col(fields, ["Image Alt Text", "image_alt_text", "Alt Text", "alt_text"])

def read_canonical_map(path: str, id_col="product_id", img_col="image_url") -> Dict[str, str]:
    m = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            pid = norm(row.get(id_col))
            img = norm(row.get(img_col))
            if pid:
                m[pid] = img
    return m

def pid_from_handle(handle: str) -> str:
    h = norm(handle)
    if not h:
        return ""
    # common: "<product_id>-product" or "<product_id>"
    if h.endswith("-product"):
        return h[:-len("-product")]
    return h

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shopify-csv", required=True)
    ap.add_argument("--canonical-csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--canonical-id-col", default="product_id")
    ap.add_argument("--canonical-img-col", default="image_url")
    ap.add_argument("--allow-placeholders", action="store_true", help="Cuenta placeholders como válidos (demo/bootstrap)")
    ap.add_argument("--force", action="store_true", help="Sobrescribe imagen aunque ya exista")
    args = ap.parse_args()

    if not os.path.exists(args.shopify_csv):
        print(f"Missing shopify CSV: {args.shopify_csv}", file=sys.stderr)
        return 2
    if not os.path.exists(args.canonical_csv):
        print(f"Missing canonical CSV: {args.canonical_csv}", file=sys.stderr)
        return 2

    canon = read_canonical_map(args.canonical_csv, args.canonical_id_col, args.canonical_img_col)
    if not canon:
        print("Canonical map vacío (no ids)", file=sys.stderr)
        return 2

    with open(args.shopify_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []

    if not rows:
        print("Shopify CSV sin filas", file=sys.stderr)
        return 2

    img_col = detect_image_col(fields)
    handle_col = detect_handle_col(fields)

    if not img_col:
        print(f"No pude detectar columna de imagen en Shopify CSV. Headers sample: {fields[:30]}", file=sys.stderr)
        return 2
    if not handle_col:
        print(f"No pude detectar columna Handle en Shopify CSV. Headers sample: {fields[:30]}", file=sys.stderr)
        return 2

    title_col = detect_title_col(fields)
    pos_col = detect_image_position_col(fields)
    alt_col = detect_image_alt_col(fields)

    total = len(rows)
    filled = 0
    kept = 0
    missing_canon = 0
    blocked_placeholder = 0

    for r in rows:
        handle = norm(r.get(handle_col))
        pid = pid_from_handle(handle)
        cur = norm(r.get(img_col))

        if cur and not args.force:
            kept += 1
            continue

        img = norm(canon.get(pid, ""))
        if not img:
            missing_canon += 1
            continue

        if (not args.allow_placeholders) and is_placeholder(img):
            blocked_placeholder += 1
            continue

        r[img_col] = img
        if pos_col and not norm(r.get(pos_col)):
            r[pos_col] = "1"
        if alt_col and not norm(r.get(alt_col)) and title_col:
            r[alt_col] = norm(r.get(title_col))[:255]
        filled += 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print("patch_shopify_images: OK")
    print(f"- shopify_in:   {args.shopify_csv}")
    print(f"- canonical:    {args.canonical_csv}")
    print(f"- out:          {args.out}")
    print(f"- cols: handle={handle_col} image={img_col} pos={pos_col} alt={alt_col}")
    print(f"- total_rows:   {total}")
    print(f"- filled:       {filled}")
    print(f"- kept:         {kept}")
    print(f"- missing_canon:{missing_canon}")
    print(f"- blocked_placeholder:{blocked_placeholder}")
    print(f"- allow_placeholders:{args.allow_placeholders}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
