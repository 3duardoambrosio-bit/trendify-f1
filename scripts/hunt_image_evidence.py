import argparse, csv, json, os, re, sys
from collections import Counter, deque

IMGISH_RE = re.compile(r"(image|img|photo|picture|media|thumbnail|gallery)", re.I)
URL_RE = re.compile(r"https?://", re.I)

DUMP_LIST_KEYS_HINT = ("items","products","data","rows","results","payload","catalog","candidates")

def read_canon_ids(path, id_col="product_id", limit=5000):
    ids = set()
    with open(path, encoding="utf-8", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            if i >= limit:
                break
            v = str(r.get(id_col) or "").strip()
            if v:
                ids.add(v)
    return ids

def quick_text_probe(path, max_bytes=2_000_000):
    try:
        with open(path, "rb") as f:
            b = f.read(max_bytes)
        t = b.decode("utf-8", errors="ignore")
    except Exception:
        return False, False
    has_http = bool(URL_RE.search(t))
    has_img = ("image" in t.lower()) or ("img" in t.lower()) or ("media" in t.lower())
    return has_http, has_img

def summarize_root(d):
    if isinstance(d, list):
        return {"type":"list","len":len(d)}
    if isinstance(d, dict):
        ks = list(d.keys())
        return {"type":"dict","keys_total":len(ks), "keys_sample":ks[:40]}
    return {"type":type(d).__name__}

def find_best_list(d):
    # Busca listas de dicts; score = dicts + img_keys*5 + url_values*5
    cands = []
    q = deque([("$", d)])
    seen = set()

    while q:
        path, node = q.popleft()
        nid = id(node)
        if nid in seen:
            continue
        seen.add(nid)

        if isinstance(node, list):
            sample = node[:80]
            dicts = [x for x in sample if isinstance(x, dict)]
            if dicts:
                img_hits = 0
                url_hits = 0
                keys = Counter()
                for it in dicts:
                    for k, v in it.items():
                        keys[k] += 1
                        if IMGISH_RE.search(str(k)):
                            img_hits += 1
                        if isinstance(v, str) and URL_RE.search(v):
                            url_hits += 1
                score = len(dicts) + (img_hits * 5) + (url_hits * 5)
                cands.append((score, path, node, len(node), len(dicts), img_hits, url_hits, keys.most_common(12)))

            for i, it in enumerate(sample[:25]):
                q.append((f"{path}[{i}]", it))

        elif isinstance(node, dict):
            # atajos: keys típicas
            for k in list(node.keys())[:200]:
                q.append((f"{path}.{k}", node[k]))

    cands.sort(key=lambda x: x[0], reverse=True)
    return cands

def load_best_list(path):
    d = json.load(open(path, "r", encoding="utf-8"))
    # shortcuts top-level
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return d, "$", {"picked":"root_list"}

    if isinstance(d, dict):
        for k in DUMP_LIST_KEYS_HINT:
            v = d.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v, f"$.{k}", {"picked":"top_key", "key":k}

    cands = find_best_list(d)
    if not cands:
        return [], "", {"picked":"none", "root":summarize_root(d)}

    score, p, node, total_len, sample_dicts, img_hits, url_hits, topkeys = cands[0]
    meta = {
        "picked":"recursive_best",
        "best_score":score,
        "best_path":p,
        "best_total_len":total_len,
        "best_sample_dicts":sample_dicts,
        "best_img_hits":img_hits,
        "best_url_hits":url_hits,
        "best_topkeys":topkeys,
        "root":summarize_root(d)
    }
    return node, p, meta

def stats_for_list(lst, canon_ids=set(), id_keys=("product_id","id","sku","handle","slug")):
    keys = Counter()
    img_key_hits = 0
    url_value_hits = 0
    id_match_hits = 0
    id_key_used = None

    # Detect best id key (si tienes canon_ids)
    if canon_ids:
        best = (None, 0)
        # mira keys globales (sample)
        sample = [x for x in lst[:120] if isinstance(x, dict)]
        if sample:
            all_keys = set()
            for it in sample:
                all_keys |= set(it.keys())
            candidates = [k for k in id_keys if k in all_keys] + [k for k in sorted(all_keys) if "id" in k.lower() or "sku" in k.lower()]
            seen=set(); candidates=[k for k in candidates if not (k in seen or seen.add(k))]
            for k in candidates[:30]:
                hits=0
                for it in sample:
                    v = str(it.get(k) or "").strip()
                    if v and v in canon_ids:
                        hits += 1
                if hits > best[1]:
                    best = (k, hits)
        id_key_used = best[0]

    for it in lst[:200]:
        if not isinstance(it, dict):
            continue
        for k, v in it.items():
            keys[k] += 1
            if IMGISH_RE.search(str(k)):
                img_key_hits += 1
            if isinstance(v, str) and URL_RE.search(v):
                url_value_hits += 1
        if canon_ids and id_key_used:
            v = str(it.get(id_key_used) or "").strip()
            if v and v in canon_ids:
                id_match_hits += 1

    return {
        "sample": min(200, len(lst)),
        "distinct_keys_sample": len(keys),
        "top_keys": keys.most_common(20),
        "img_key_hits": img_key_hits,
        "url_value_hits": url_value_hits,
        "id_key_used": id_key_used,
        "id_match_hits": id_match_hits
    }

def iter_json_files(root):
    for base, _, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".json"):
                yield os.path.join(base, fn)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/evidence", help="carpeta a escanear")
    ap.add_argument("--canonical", default="", help="canonical_products.csv para medir match IDs")
    ap.add_argument("--id-col", default="product_id")
    ap.add_argument("--limit", type=int, default=60, help="max archivos a reportar")
    args = ap.parse_args()

    canon_ids = set()
    if args.canonical and os.path.exists(args.canonical):
        canon_ids = read_canon_ids(args.canonical, id_col=args.id_col)

    reports = []
    for path in iter_json_files(args.root):
        has_http, has_img = quick_text_probe(path)
        # si no tiene ni http ni palabras tipo imagen, baja prioridad pero no lo descartes por completo
        try:
            lst, lst_path, meta = load_best_list(path)
        except Exception:
            continue
        if not lst:
            continue
        st = stats_for_list(lst, canon_ids=canon_ids)
        score = (st["url_value_hits"] * 10) + (st["img_key_hits"] * 5) + (st["id_match_hits"] * 3) + (1 if has_http else 0) + (1 if has_img else 0)
        reports.append((score, path, lst_path, meta, st))

    reports.sort(key=lambda x: x[0], reverse=True)
    print("evidence_hunt: OK")
    print(f"- root: {args.root}")
    print(f"- canonical: {args.canonical or '(none)'}")
    print(f"- files_scanned: {len(list(iter_json_files(args.root)))}")
    print(f"- candidates_found: {len(reports)}")
    print("")
    for i, (score, path, lst_path, meta, st) in enumerate(reports[:args.limit], start=1):
        print(f"[{i}] score={score}  file={path}")
        print(f"    list_path={lst_path}  pick={meta.get('picked')}  best_score={meta.get('best_score', '')}")
        print(f"    sample={st['sample']} distinct_keys={st['distinct_keys_sample']}")
        print(f"    url_value_hits={st['url_value_hits']} img_key_hits={st['img_key_hits']}")
        if st.get("id_key_used"):
            print(f"    id_key_used={st['id_key_used']} id_match_hits(sample)={st['id_match_hits']}")
        print(f"    top_keys={st['top_keys']}")
        print("")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
