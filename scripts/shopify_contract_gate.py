import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)
URL_RE = re.compile(r"^https?://", re.I)

DEFAULT_REQUIRED_COLS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Status",
    "Variant Price",
]

def is_placeholder(u: str) -> bool:
    return bool(u) and bool(PLACEHOLDER_RE.search(u.strip()))

def pick_image_columns(fieldnames):
    # Shopify typical
    preferred = ["Image Src", "Variant Image", "Image URL", "Image"]
    lower_map = {c.lower(): c for c in fieldnames}
    for p in preferred:
        if p in fieldnames:
            return [p]
        if p.lower() in lower_map:
            return [lower_map[p.lower()]]

    # Fallback heuristic: any column containing both "image" and ("src" or "url")
    cols = []
    for c in fieldnames:
        lc = c.lower()
        if "image" in lc and ("src" in lc or "url" in lc):
            cols.append(c)
    return cols

def to_float(x: str):
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s2 = re.sub(r"[^\d\.]", "", s)
    try:
        return float(s2)
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", help="Ruta al CSV tipo Shopify")
    ap.add_argument("--mode", choices=["demo", "prod"], default="demo", help="demo = tolerante; prod = estricto")
    ap.add_argument("--allow-placeholders", action="store_true", help="En demo, baja placeholders a WARNING")
    ap.add_argument("--fail-on-warn", action="store_true", help="Si hay warnings, falla (exit!=0)")
    ap.add_argument("--report-out", default=None, help="Ruta del JSON report (default: <csv>.contract_report.json)")
    args = ap.parse_args()

    csv_path = args.csv_path
    if not os.path.exists(csv_path):
        print(f"Missing CSV: {csv_path}", file=sys.stderr)
        return 2

    report_out = args.report_out or (csv_path + ".contract_report.json")

    errors = []
    warnings = []

    # Read
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames or []
        rows = list(r)

    # Column-level checks
    missing_cols = [c for c in DEFAULT_REQUIRED_COLS if c not in fieldnames]
    if missing_cols:
        # Esto sí es estructural; lo marcamos como error único
        errors.append({
            "type": "missing_required_columns",
            "line": 0,
            "handle": "",
            "value": ", ".join(missing_cols),
            "note": "CSV no cumple columnas mínimas Shopify"
        })

    image_cols = pick_image_columns(fieldnames)

    # Row-level checks
    handles = []
    for i, row in enumerate(rows, start=2):  # header=1, first data line=2
        handle = (row.get("Handle") or "").strip()
        title = (row.get("Title") or "").strip()
        body = (row.get("Body (HTML)") or "").strip()
        price_s = (row.get("Variant Price") or "").strip()

        if not handle:
            errors.append({"type": "missing_handle", "line": i, "handle": "", "value": "", "note": "Handle vacío"})
        else:
            handles.append(handle)

        if not title:
            warnings.append({"type": "missing_title", "line": i, "handle": handle, "value": "", "note": "Title vacío"})

        if not body:
            warnings.append({"type": "missing_body", "line": i, "handle": handle, "value": "", "note": "Body (HTML) vacío"})

        price = to_float(price_s)
        if price is None or price <= 0:
            errors.append({"type": "invalid_price", "line": i, "handle": handle, "value": price_s, "note": "Variant Price inválido"})

        # Image checks (only if column exists)
        img_val = ""
        for c in image_cols:
            v = (row.get(c) or "").strip()
            if v:
                img_val = v
                break

        if img_val:
            if not URL_RE.search(img_val):
                # En demo lo toleramos como warning si trae "algo"; en prod es error
                if args.mode == "demo":
                    warnings.append({"type": "image_not_http", "line": i, "handle": handle, "value": img_val[:180], "note": "Imagen no http(s)"})
                else:
                    errors.append({"type": "image_not_http", "line": i, "handle": handle, "value": img_val[:180], "note": "Imagen no http(s)"})
            elif is_placeholder(img_val):
                # AQUÍ está el bug de tu vida hoy: placeholders
                if args.mode == "demo" and args.allow_placeholders:
                    warnings.append({"type": "image_placeholder_allowed", "line": i, "handle": handle, "value": img_val[:180], "note": "Placeholder permitido en demo"})
                else:
                    errors.append({"type": "image_placeholder_blocked", "line": i, "handle": handle, "value": img_val[:180], "note": "Placeholder bloqueado"})
        else:
            # Sin imagen
            if args.mode == "demo":
                warnings.append({"type": "missing_image", "line": i, "handle": handle, "value": "", "note": "Sin imagen"})
            else:
                errors.append({"type": "missing_image", "line": i, "handle": handle, "value": "", "note": "Sin imagen"})

    # Uniqueness check
    hc = Counter(handles)
    dups = [h for h, c in hc.items() if c > 1]
    if dups:
        errors.append({"type": "duplicate_handles", "line": 0, "handle": "", "value": ", ".join(dups[:30]), "note": "Handles duplicados"})

    rep = {
        "csv_path": csv_path,
        "mode": args.mode,
        "allow_placeholders": bool(args.allow_placeholders),
        "fail_on_warn": bool(args.fail_on_warn),
        "rows": len(rows),
        "unique_handles": len(set(handles)),
        "errors": errors,
        "warnings": warnings,
    }

    os.makedirs(os.path.dirname(report_out) or ".", exist_ok=True)
    with open(report_out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print(f"CONTRACT_GATE_REPORT: {report_out}")
    print(f"MODE: {args.mode} FAIL_ON_WARN: {args.fail_on_warn}")
    print(f"ROWS: {len(rows)} UNIQUE_HANDLES: {len(set(handles))}")
    print(f"ERRORS: {len(errors)} WARNINGS: {len(warnings)}")

    if len(errors) > 0:
        return 1
    if args.fail_on_warn and len(warnings) > 0:
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
