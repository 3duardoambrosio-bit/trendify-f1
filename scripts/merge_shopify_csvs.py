import csv
from pathlib import Path
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True, help="Ruta a exports/releases/_batch/<sha>")
    ap.add_argument("--out", default=None, help="Nombre de salida (default: shopify_import_all.csv dentro del batch)")
    args = ap.parse_args()

    batch = Path(args.batch)
    canonical = batch / "canonical_products.csv"
    if not canonical.exists():
        raise SystemExit(f"NO_EXISTE: {canonical}")

    out = Path(args.out) if args.out else (batch / "shopify_import_all.csv")

    # lee product_ids del canonical
    pids = []
    with canonical.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or "product_id" not in r.fieldnames:
            raise SystemExit(f"canonical sin product_id. headers={r.fieldnames}")
        for row in r:
            pid = (row.get("product_id") or "").strip()
            if pid:
                pids.append(pid)

    rows_written = 0
    header = None

    with out.open("w", encoding="utf-8-sig", newline="") as fo:
        w = None
        for pid in pids:
            fpath = Path("exports") / pid / "shopify" / "shopify_products.csv"
            if not fpath.exists():
                print(f"WARN: faltó {fpath}")
                continue

            with fpath.open("r", encoding="utf-8-sig", newline="") as fi:
                rr = csv.DictReader(fi)
                if not rr.fieldnames:
                    print(f"WARN: CSV vacío {fpath}")
                    continue

                if header is None:
                    header = rr.fieldnames
                    w = csv.DictWriter(fo, fieldnames=header)
                    w.writeheader()
                else:
                    if rr.fieldnames != header:
                        print(f"WARN: headers distintos en {fpath}")

                for row in rr:
                    w.writerow(row)
                    rows_written += 1

    print("MERGE_OK")
    print("canonical_ids=", len(pids))
    print("rows_written=", rows_written)
    print("out=", out)

if __name__ == "__main__":
    main()
