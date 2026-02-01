import argparse, csv, json, os, re, sys
from collections import deque

PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)
IMGISH_RE = re.compile(r"(image|img|photo|picture|media|thumbnail|gallery)", re.I)
IDISH_RE = re.compile(r"(id|sku|handle|slug|external|source|vendor|dropi)", re.I)

CANDIDATE_KEYS = [
    "image_url","image","img","thumbnail","thumb","featured_image","featuredImage",
    "main_image","mainImage","cover","cover_url","coverUrl","photo","picture",
    "imageUrl","imageURL","image_link","imageLink","image_src","imageSrc",
    "images","media","gallery","photos","pictures","assets"
]

DUMP_ID_CANDIDATES = [
    "product_id","id","sku","handle","slug","external_id","source_id",
    "dropi_id","dropi_product_id","vendor_product_id"
]

WRAPPER_KEYS = ("source","product","item","data","payload","record")

def is_placeholder(url: str) -> bool:
    if not url:
        return False
    return bool(PLACEHOLDER_RE.search(str(url).strip()))

def first_url_from_anything(x):
    if x is None:
        return None, "none"
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("http"):
            return s, "str"
        return None, "str_nohttp"
    if isinstance(x, dict):
        for k in ("url","src","href","link","secure_url","original","large","medium","small"):
            v = x.get(k)
            if isinstance(v, str) and v.strip().startswith("http"):
                return v.strip(), f"dict.{k}"
        for k, v in x.items():
            u, why = first_url_from_anything(v)
            if u:
                return u, f"dict_nested.{k}->{why}"
        return None, "dict_nourl"
    if isinstance(x, list):
        for i, it in enumerate(x):
            u, why = first_url_from_anything(it)
            if u:
                return u, f"list[{i}].{why}"
        return None, "list_empty"
    return None, f"unknown_type:{type(x).__name__}"

def extract_image(product: dict, allow_placeholders: bool):
    # 0) wrappers típicos (candidates -> source)
    for wk in WRAPPER_KEYS:
        v = product.get(wk)
        if isinstance(v, dict):
            u, why = extract_image(v, allow_placeholders)
            if u:
                return u, f"{wk}->{why}"

    # 1) keys directos
    for k in CANDIDATE_KEYS:
        if k in product:
            u, why = first_url_from_anything(product.get(k))
            if u:
                if (not allow_placeholders) and is_placeholder(u):
                    continue
                return u, f"top.{k}:{why}"

    # 2) variants -> images
    v = product.get("variants")
    if isinstance(v, list):
        for vi, vv in enumerate(v):
            if isinstance(vv, dict):
                for k in ("image","image_url","imageUrl","featured_image","media","images"):
                    if k in vv:
                        u, why = first_url_from_anything(vv.get(k))
                        if u:
                            if (not allow_placeholders) and is_placeholder(u):
                                continue
                            return u, f"variants[{vi}].{k}:{why}"

    # 3) heurística por keys que parezcan imagen
    for k, val in product.items():
        if IMGISH_RE.search(str(k)):
            u, why = first_url_from_anything(val)
            if u:
                if (not allow_placeholders) and is_placeholder(u):
                    continue
                return u, f"heur.{k}:{why}"

    # 4) último recurso: deep scan limitado buscando primer http(s)
    # (evita explotar; pero rescata estructuras raras)
    q = deque([product])
    seen = set()
    depth = 0
    while q and depth < 200:
        node = q.popleft()
        depth += 1
        if id(node) in seen:
            continue
        seen.add(id(node))
        u, why = first_url_from_anything(node)
        if u:
            if (not allow_placeholders) and is_placeholder(u):
                pass
            else:
                return u, f"deep:{why}"
        if isinstance(node, dict):
            for vv in list(node.values())[:50]:
                if isinstance(vv, (dict, list)):
                    q.append(vv)
        elif isinstance(node, list):
            for vv in node[:50]:
                if isinstance(vv, (dict, list)):
                    q.append(vv)

    return "", "not_found"

def summarize_root(d):
    if isinstance(d, list):
        return {"type":"list","len":len(d)}
    if isinstance(d, dict):
        return {"type":"dict","keys":sorted(list(d.keys()))[:60], "keys_total":len(d.keys())}
    return {"type":type(d).__name__}

def find_best_list(d, want_id_key="product_id"):
    candidates = []
    q = deque()
    q.append(("$", d))
    seen = set()

    while q:
        path, node = q.popleft()
        nid = id(node)
        if nid in seen:
            continue
        seen.add(nid)

        if isinstance(node, list):
            sample = node[:50]
            dicts = [x for x in sample if isinstance(x, dict)]
            if dicts:
                id_hits = 0
                img_hits = 0
                for it in dicts:
                    for k in it.keys():
                        if k == want_id_key or k in DUMP_ID_CANDIDATES or IDISH_RE.search(str(k)):
                            id_hits += 1
                            break
                    if any(IMGISH_RE.search(str(k)) for k in it.keys()):
                        img_hits += 1
                score = len(dicts) + (id_hits * 10) + (img_hits * 5)
                candidates.append((score, path, node, len(node), len(dicts), id_hits, img_hits))
            for i, it in enumerate(sample[:30]):
                q.append((f"{path}[{i}]", it))

        elif isinstance(node, dict):
            for k, v in list(node.items())[:200]:
                q.append((f"{path}.{k}", v))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates

def load_dump_auto(path: str, want_id_key="product_id"):
    d = json.load(open(path, "r", encoding="utf-8"))
    if isinstance(d, list):
        return d, "$", {"picked":"root_list"}

    if isinstance(d, dict):
        for k in ("items","products","data","rows","results","payload","catalog","candidates"):
            v = d.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v, f"$.{k}", {"picked":"top_level_key", "key":k}

    candidates = find_best_list(d, want_id_key=want_id_key)
    if not candidates:
        return [], "", {"picked":"none", "root":summarize_root(d)}

    score, path0, node0, total_len, sample_dicts, id_hits, img_hits = candidates[0]
    meta = {
        "picked":"recursive_best",
        "best_path":path0,
        "best_score":score,
        "best_total_len":total_len,
        "best_sample_dicts":sample_dicts,
        "best_id_hits":id_hits,
        "best_img_hits":img_hits,
        "root":summarize_root(d),
        "top_candidates":[
            {"path":p,"score":s,"len":l,"sample_dicts":sd,"id_hits":ih,"img_hits":mh}
            for (s,p,_,l,sd,ih,mh) in candidates[:5]
        ]
    }
    return node0, path0, meta

def read_csv(path: str):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def detect_best_join(canon_rows, dump_items):
    if not canon_rows:
        return "product_id", "product_id", 0

    canon_fields = list(canon_rows[0].keys())
    canon_id_cols = []
    for c in canon_fields:
        lc = c.lower()
        if lc in ("product_id","id","sku","handle","slug"):
            canon_id_cols.append(c)
        elif ("id" in lc or "sku" in lc) and (("dropi" in lc) or ("source" in lc) or ("vendor" in lc) or ("external" in lc) or ("origin" in lc)):
            canon_id_cols.append(c)
        elif IDISH_RE.search(lc):
            canon_id_cols.append(c)
    seen=set(); canon_id_cols=[x for x in canon_id_cols if not (x in seen or seen.add(x))]

    dump_id_keys = []
    if dump_items and isinstance(dump_items[0], dict):
        keys = set()
        for it in dump_items[:80]:
            if isinstance(it, dict):
                keys |= set(it.keys())
                # también keys dentro de source
                src = it.get("source")
                if isinstance(src, dict):
                    keys |= set(src.keys())

        for k in DUMP_ID_CANDIDATES:
            if k in keys:
                dump_id_keys.append(k)
        for k in sorted(keys):
            if k not in dump_id_keys and IDISH_RE.search(k):
                dump_id_keys.append(k)

    dump_sets = {}
    for dk in dump_id_keys:
        s=set()
        for it in dump_items:
            if isinstance(it, dict):
                v = it.get(dk)
                if v is None and isinstance(it.get("source"), dict):
                    v = it["source"].get(dk)
                if v is None:
                    continue
                v = str(v).strip()
                if v:
                    s.add(v)
        if s:
            dump_sets[dk]=s

    best = ("product_id","product_id",0)
    sample = canon_rows[:200]
    for cc in canon_id_cols:
        for dk, dset in dump_sets.items():
            hits=0
            for r in sample:
                v = str(r.get(cc) or "").strip()
                if v and v in dset:
                    hits += 1
            if hits > best[2]:
                best = (cc, dk, hits)

    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, help="JSON dump (estructura variable)")
    ap.add_argument("--canonical", required=True, help="canonical_products.csv")
    ap.add_argument("--out", required=True, help="salida patched canonical CSV")
    ap.add_argument("--id-col", default="product_id", help="columna id en canonical (fallback)")
    ap.add_argument("--dump-id", default="product_id", help="campo id preferido en dump (fallback)")
    ap.add_argument("--allow-placeholders", action="store_true", help="Cuenta placeholders como imágenes válidas (solo dev/bootstrap)")
    args = ap.parse_args()

    dump_items, dump_path, dump_meta = load_dump_auto(args.dump, want_id_key=args.dump_id)
    if not dump_items:
        print("patch_images: FAIL (no pude auto-encontrar lista de productos dentro del dump)", file=sys.stderr)
        print("dump_meta:", dump_meta, file=sys.stderr)
        return 2

    canon_rows = read_csv(args.canonical)

    canon_join_col, dump_join_key, join_hits = detect_best_join(canon_rows, dump_items)
    if join_hits == 0:
        canon_join_col, dump_join_key = args.id_col, args.dump_id

    id2img = {}
    dump_images_found = 0
    for it in dump_items:
        if not isinstance(it, dict):
            continue
        pid = str(it.get(dump_join_key) or "").strip()
        if not pid and isinstance(it.get("source"), dict):
            pid = str(it["source"].get(dump_join_key) or "").strip()
        if not pid:
            continue
        img, _why = extract_image(it, allow_placeholders=args.allow_placeholders)
        if img:
            id2img[pid] = img
            dump_images_found += 1

    filled = 0
    had = 0
    missing = 0
    for r in canon_rows:
        canon_id = str(r.get(canon_join_col) or "").strip()
        cur = str(r.get("image_url") or "").strip()
        if cur:
            had += 1
            continue
        if canon_id and canon_id in id2img:
            r["image_url"] = id2img[canon_id]
            filled += 1
        else:
            missing += 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=canon_rows[0].keys() if canon_rows else ["product_id","title","image_url"])
        w.writeheader()
        w.writerows(canon_rows)

    print("patch_images: OK")
    print(f"- dump:          {args.dump}")
    print(f"- dump_list_path:{dump_path}")
    print(f"- dump_meta_pick:{dump_meta.get('picked')}")
    if dump_meta.get("top_candidates"):
        print(f"- dump_top_candidates: {dump_meta['top_candidates']}")
    print(f"- canonical_in:  {args.canonical}")
    print(f"- out:           {args.out}")
    print(f"- canonical_rows:{len(canon_rows)}")
    print(f"- join: canonical.{canon_join_col}  <->  dump.{dump_join_key}  (sample_hits={join_hits})")
    print(f"- dump_images_found: {dump_images_found} (allow_placeholders={args.allow_placeholders})")
    print(f"- already_had:   {had}")
    print(f"- filled_now:    {filled}")
    print(f"- still_missing: {missing}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
