import json, re, sys
from collections import Counter

IMGISH_RE = re.compile(r"(image|img|photo|picture|media|thumbnail|gallery)", re.I)
URLISH_RE = re.compile(r"(url|link|href|permalink|slug)", re.I)

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def pick_candidates(d):
    if isinstance(d, dict) and isinstance(d.get("candidates"), list):
        return d["candidates"], "$.candidates"
    # fallback ultra simple
    return [], ""

def scan(obj, max_items=20):
    if not obj:
        return
    keys = Counter()
    img_keys = Counter()
    url_keys = Counter()
    http_values = 0
    nonhttp_urlish_values = 0

    for it in obj[:max_items]:
        if not isinstance(it, dict):
            continue
        for k, v in it.items():
            keys[k] += 1
            if IMGISH_RE.search(k):
                img_keys[k] += 1
            if URLISH_RE.search(k):
                url_keys[k] += 1
            if isinstance(v, str):
                s = v.strip()
                if "http" in s:
                    http_values += 1
                elif URLISH_RE.search(k) and s:
                    nonhttp_urlish_values += 1

    print("probe_dump: OK")
    print(f"- sample_items: {min(max_items, len(obj))}")
    print(f"- distinct_keys_in_sample: {len(keys)}")
    print(f"- top_keys: {keys.most_common(25)}")
    print(f"- image_like_keys: {img_keys.most_common(25)}")
    print(f"- url_like_keys: {url_keys.most_common(25)}")
    print(f"- http_strings_in_sample_values: {http_values}")
    print(f"- nonhttp_urlish_strings_in_sample_values: {nonhttp_urlish_values}")

def show_examples(obj, key_candidates, limit=5):
    shown = 0
    for it in obj:
        if not isinstance(it, dict):
            continue
        for k in key_candidates:
            if k in it and isinstance(it[k], str) and it[k].strip():
                print(f"example: {k} = {it[k][:200]}")
                shown += 1
                if shown >= limit:
                    return

def main():
    if len(sys.argv) < 2:
        print("usage: python probe_dropi_dump.py <dump.json>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    d = load(path)
    cands, cpath = pick_candidates(d)
    if not cands:
        print("probe_dump: FAIL (no candidates list found at $.candidates)", file=sys.stderr)
        if isinstance(d, dict):
            print("root_keys:", list(d.keys())[:80], file=sys.stderr)
        return 2

    print(f"dump_path: {path}")
    print(f"candidates_path: {cpath}")
    print(f"candidates_len: {len(cands)}")
    scan(cands, max_items=20)

    # ejemplos de keys típicas por si existen
    print("")
    print("examples (if present):")
    show_examples(cands, ["product_url","url","link","permalink","href","handle","slug","source_url","productLink"], limit=10)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
