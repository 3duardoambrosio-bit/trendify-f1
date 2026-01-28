import csv
import json
import re
from pathlib import Path
import argparse

REQUIRED = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Tags",
    "Published",
    "Option1 Name",
    "Option1 Value",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Status",
    "Image Src",
]

ALLOWED_STATUS = {"active", "draft", "archived"}
ALLOWED_BOOL = {"TRUE", "FALSE"}

def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")

def _to_float(s: str):
    s = (s or "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return "NaN"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", help="Ruta al CSV tipo Shopify")
    ap.add_argument("--min-rows", type=int, default=1)
    args = ap.parse_args()

    p = Path(args.csv_path)
    if not p.exists():
        raise SystemExit(f"NO_EXISTE: {p}")

    report_path = p.with_suffix(p.suffix + ".contract_report.json")

    errors = []
    warns = []
    stats = {
        "rows": 0,
        "unique_handles": 0,
        "has_demo_handles": 0,
        "placeholder_images": 0,
        "price_ok": 0,
        "price_bad": 0,
    }

    handles = set()

    with p.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        headers = r.fieldnames or []
        missing = [c for c in REQUIRED if c not in headers]
        if missing:
            errors.append({"type": "missing_columns", "missing": missing, "headers": headers})

        for i, row in enumerate(r, start=2):  # header = line 1
            stats["rows"] += 1

            handle = (row.get("Handle") or "").strip()
            title = (row.get("Title") or "").strip()
            body = (row.get("Body (HTML)") or "").strip()
            vendor = (row.get("Vendor") or "").strip()
            published = (row.get("Published") or "").strip().upper()
            status = (row.get("Status") or "").strip().lower()
            img = (row.get("Image Src") or "").strip()
            price = _to_float(row.get("Variant Price") or "")

            if handle:
                if handle in handles:
                    errors.append({"type": "dup_handle", "line": i, "handle": handle})
                handles.add(handle)
                if handle.startswith("demo_"):
                    stats["has_demo_handles"] += 1
            else:
                errors.append({"type": "empty_handle", "line": i})

            if not title:
                errors.append({"type": "empty_title", "line": i})
            if len(body) < 10:
                errors.append({"type": "body_too_short", "line": i, "len": len(body)})
            if not vendor:
                warns.append({"type": "empty_vendor", "line": i})

            if published and published not in ALLOWED_BOOL:
                errors.append({"type": "bad_published", "line": i, "value": published})

            if status and status not in ALLOWED_STATUS:
                errors.append({"type": "bad_status", "line": i, "value": status})

            if not img:
                errors.append({"type": "missing_image", "line": i})
            else:
                if not _is_url(img):
                    errors.append({"type": "bad_image_url", "line": i, "value": img})
                if "via.placeholder.com" in img:
                    stats["placeholder_images"] += 1
                    warns.append({"type": "placeholder_image", "line": i, "value": img})

            if price is None:
                errors.append({"type": "missing_price", "line": i})
            elif price == "NaN" or price <= 0:
                stats["price_bad"] += 1
                errors.append({"type": "bad_price", "line": i, "value": row.get("Variant Price")})
            else:
                stats["price_ok"] += 1

    stats["unique_handles"] = len(handles)

    if stats["rows"] < args.min_rows:
        errors.append({"type": "too_few_rows", "rows": stats["rows"], "min_rows": args.min_rows})

    # “Modo demo” no es error, pero sí lo reportamos
    if stats["has_demo_handles"] == stats["rows"] and stats["rows"] > 0:
        warns.append({"type": "demo_mode_detected", "note": "Todos los handles parecen demo_. Esto valida pipeline, no mercado real."})

    report = {
        "csv": str(p),
        "stats": stats,
        "errors_count": len(errors),
        "warnings_count": len(warns),
        "errors": errors[:200],   # cap
        "warnings": warns[:200],  # cap
        "pass": len(errors) == 0,
    }

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CONTRACT_GATE_REPORT:", report_path)
    print("ROWS:", stats["rows"], "UNIQUE_HANDLES:", stats["unique_handles"])
    print("ERRORS:", len(errors), "WARNINGS:", len(warns))

    if len(errors) > 0:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
