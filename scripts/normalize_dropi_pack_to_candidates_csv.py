import argparse, json, re
from pathlib import Path

CANON_MAP = {
  "candidate_id": ["candidate_id","id","product_id","productId","sku","handle","uuid"],
  "title": ["title","name","product_name","productName"],
  "price": ["price","price_mxn","sale_price","finalPrice","final_price","priceMXN","precio","priceValue"],
  "rating": ["rating","stars","avg_rating","averageRating","ratingValue","calificacion"],
  "reviews": ["reviews","reviewsCount","rating_count","num_reviews","reviewCount","totalReviews"],
  "sold": ["sold","orders","soldCount","total_sales","sales","totalOrders","ordenes","ventas"],
  "url": ["url","product_url","link","productLink","permalink"],
  "image_url": ["image_url","image","img","thumbnail","imageUrl","mainImage","cover","coverImage"]
}

def pick(row, keys, default=None):
    for k in keys:
        if k in row:
            v = row.get(k)
            if v not in (None, "", "null", "None"):
                return v
    return default

_num_re = re.compile(r"[^0-9.\-]+")

def to_float(v):
    if v is None: 
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # quitar moneda, texto, espacios, comas
    s = s.replace(",", "")
    s = _num_re.sub("", s)
    try:
        return float(s)
    except:
        return None

def to_int(v):
    f = to_float(v)
    if f is None:
        return 0
    try:
        return int(round(f))
    except:
        return 0

def extract_rows(raw):
    # list directo
    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        # 1) llaves comunes directas
        for k in ("top","items","products","candidates","rows","data"):
            if k in raw:
                v = raw.get(k)
                if isinstance(v, list):
                    return v
                if isinstance(v, dict):
                    # data anidada
                    for kk in ("items","products","rows","candidates","top"):
                        if kk in v and isinstance(v[kk], list):
                            return v[kk]
                    # dict id->obj
                    if v and all(isinstance(x, dict) for x in v.values()):
                        return list(v.values())

        # 2) buscar cualquier lista grande dentro del dict (fallback)
        best = []
        for _, v in raw.items():
            if isinstance(v, list) and len(v) > len(best):
                best = v
            elif isinstance(v, dict):
                for _, vv in v.items():
                    if isinstance(vv, list) and len(vv) > len(best):
                        best = vv
        return best

    return []

def normalize(raw, src_meta=None):
    rows = extract_rows(raw)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue

        item = {}
        item["candidate_id"] = pick(r, CANON_MAP["candidate_id"], default=None)
        item["title"]        = pick(r, CANON_MAP["title"], default="").strip() if pick(r, CANON_MAP["title"], default="") else ""
        item["price"]        = to_float(pick(r, CANON_MAP["price"], default=None)) or 0.0
        item["rating"]       = to_float(pick(r, CANON_MAP["rating"], default=None)) or 0.0
        item["reviews"]      = to_int(pick(r, CANON_MAP["reviews"], default=0))
        item["sold"]         = to_int(pick(r, CANON_MAP["sold"], default=0))
        item["url"]          = pick(r, CANON_MAP["url"], default="")
        item["image_url"]    = pick(r, CANON_MAP["image_url"], default="")

        # meta extra si viene en el pack
        if src_meta:
            item["source"] = src_meta.get("source","")
            item["generated_at"] = src_meta.get("generated_at","")

        # si no hay id, fabrica uno estable-ish con title+price
        if not item["candidate_id"]:
            item["candidate_id"] = f"anon::{item['title'][:40]}::{item['price']:.2f}"

        out.append(item)

    return out

def write_csv(rows, out_path: Path):
    import csv
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["candidate_id","title","price","rating","reviews","sold","url","image_url","source","generated_at"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k,"") for k in cols})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    p = Path(args.inp)
    raw = json.loads(p.read_text(encoding="utf-8"))

    src_meta = {}
    if isinstance(raw, dict):
        src_meta = {k: raw.get(k) for k in ("source","generated_at") if k in raw}

    rows = normalize(raw, src_meta=src_meta)

    if args.limit and args.limit > 0:
        rows = rows[:args.limit]

    if not rows:
        raise SystemExit(f"[FATAL] 0 candidates after normalization. Check pack structure: keys={list(raw.keys()) if isinstance(raw,dict) else type(raw)}")

    write_csv(rows, Path(args.out))
    print(f"[OK] wrote {len(rows)} rows -> {args.out}")
    # mini-sample
    for i, r in enumerate(rows[:5], start=1):
        print(f"  {i:02d} | rating={r['rating']:.2f} reviews={r['reviews']} sold={r['sold']} price={r['price']:.2f} | {r['title'][:70]}")

if __name__ == "__main__":
    main()
