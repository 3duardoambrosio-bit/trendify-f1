import csv, re, sys
from collections import Counter

CSV_PATH = r"data\evidence\dropi_catalog_export_REAL.csv"
IMG_COL = "image_url"
PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)

def domain(u: str):
    m = re.search(r"https?://([^/]+)/", u)
    return (m.group(1).lower() if m else "")

def main():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        fields = r.fieldnames or []
        print("probe_catalog_csv: OK")
        print("- csv:", CSV_PATH)
        print("- columns(image/url-ish):", [c for c in fields if ("image" in c.lower() or "url" in c.lower())][:80])
        total=blank=http=placeholder=0
        doms=Counter()
        samples=[]
        for row in r:
            total += 1
            u = (row.get(IMG_COL) or "").strip()
            if not u:
                blank += 1
                continue
            if u.startswith("http"):
                http += 1
            if PLACEHOLDER_RE.search(u):
                placeholder += 1
            d = domain(u)
            if d:
                doms[d] += 1
            if len(samples) < 5:
                samples.append(u[:160])
        print(f"- total_rows: {total}")
        print(f"- image_url_blank: {blank}")
        print(f"- image_url_http:  {http}")
        print(f"- image_url_placeholder_hits: {placeholder}")
        print(f"- top_domains: {doms.most_common(10)}")
        print("- samples:", samples)

if __name__ == "__main__":
    raise SystemExit(main())
