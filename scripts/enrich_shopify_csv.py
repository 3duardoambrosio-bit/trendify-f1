from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


CANDIDATE_TEXT_KEYS = (
    "body_html",
    "body",
    "description",
    "product_description",
    "long_description",
    "primary_text",
    "caption",
    "headline",
    "copy",
    "ad_copy",
    "value_prop",
)


def _read_text(p: Path) -> str:
    b = p.read_bytes()
    # tolerate BOM if present
    if b.startswith(b"\xef\xbb\xbf"):
        return b.decode("utf-8-sig")
    return b.decode("utf-8")


def _write_text_utf8_nobom_lf(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


def _best_text_from_creatives(ndjson_path: Path) -> str:
    if not ndjson_path.exists():
        return ""
    best = ""
    with ndjson_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue

            # grab candidate fields
            for k in CANDIDATE_TEXT_KEYS:
                v = obj.get(k)
                if isinstance(v, str):
                    t = v.strip()
                    if len(t) > len(best):
                        best = t

            # also scan any string fields (fallback)
            for v in obj.values():
                if isinstance(v, str):
                    t = v.strip()
                    if len(t) > len(best):
                        best = t
    return best.strip()


def _canonical_desc(canonical_csv: Path | None, product_id: str) -> tuple[str, str]:
    # returns (title, description)
    if not canonical_csv or not canonical_csv.exists():
        return ("", "")
    with canonical_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("product_id") or "").strip() == product_id:
                return ((row.get("title") or "").strip(), (row.get("description") or "").strip())
    return ("", "")


def _merge_tags(existing: str, add: list[str]) -> str:
    raw = [x.strip() for x in (existing or "").split(",") if x.strip()]
    s = {x.lower(): x for x in raw}
    for t in add:
        if not t:
            continue
        key = t.strip().lower()
        if key and key not in s:
            s[key] = t.strip()
    # keep deterministic-ish output: original order + added order
    out = raw[:]
    for t in add:
        key = t.strip().lower()
        if key and all(x.lower() != key for x in out):
            out.append(s[key])
    return ", ".join([x for x in out if x.strip()])


def _htmlify(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    # If it already looks like HTML, don't overthink it
    if "<p" in t or "<br" in t or "<ul" in t or "<div" in t:
        return t
    # basic HTML wrap
    lines = [x.strip() for x in t.splitlines() if x.strip()]
    if len(lines) <= 1:
        return f"<p>{t}</p>"
    # if multiple lines, bullets
    items = "".join([f"<li>{x}</li>" for x in lines])
    return f"<ul>{items}</ul>"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit-dir", required=True)
    ap.add_argument("--canonical-csv", default="")
    ap.add_argument("--vendor", default="TrendifyHub")
    ap.add_argument("--force", action="store_true", help="overwrite Body (HTML) even if not empty")
    args = ap.parse_args(argv)

    kit_dir = Path(args.kit_dir)
    canonical_csv = Path(args.canonical_csv) if args.canonical_csv else None

    shop_csv = kit_dir / "shopify" / "shopify_products.csv"
    creatives = kit_dir / "creatives.ndjson"

    if not shop_csv.exists():
        print(f"ERROR: missing shopify csv: {shop_csv}")
        return 2

    # Read existing CSV
    with shop_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not fieldnames or "Handle" not in fieldnames:
        print("ERROR: shopify csv missing headers")
        return 3

    # Ensure required columns exist
    required = ["Handle", "Title", "Body (HTML)", "Vendor", "Tags", "Status"]
    for col in required:
        if col not in fieldnames:
            fieldnames.append(col)

    # Determine product_id (we assume kit_dir name = product_id)
    product_id = kit_dir.name

    # Build best body
    best_from_creatives = _best_text_from_creatives(creatives)
    can_title, can_desc = _canonical_desc(canonical_csv, product_id)
    fallback_title = can_title

    # Prefer creatives, then canonical description
    body_source = best_from_creatives or can_desc

    # Write rows back with enriched fields
    new_rows: list[dict[str, Any]] = []
    for row in rows:
        title = (row.get("Title") or "").strip() or fallback_title or product_id
        body = (row.get("Body (HTML)") or "").strip()

        if args.force or not body:
            html = _htmlify(body_source)
            if not html:
                html = f"<p><strong>{title}</strong></p><p>Descripción en proceso (SYNAPSE).</p>"
            row["Body (HTML)"] = html

        if not (row.get("Vendor") or "").strip():
            row["Vendor"] = args.vendor

        # Always ensure tags contain synapse/wavekit (dedup)
        row["Tags"] = _merge_tags((row.get("Tags") or ""), ["synapse", "wavekit"])

        # Keep Status unless empty
        if not (row.get("Status") or "").strip():
            row["Status"] = "draft"

        # Ensure Title present
        if not (row.get("Title") or "").strip():
            row["Title"] = title

        new_rows.append(row)

    # Write back with LF and UTF-8 no BOM
    out_lines = []
    import io
    buf = io.StringIO(newline="\n")
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    w.writeheader()
    for r in new_rows:
        w.writerow({k: r.get(k, "") for k in fieldnames})
    _write_text_utf8_nobom_lf(shop_csv, buf.getvalue())

    print("enrich_shopify_csv: OK")
    print(f"- csv: {shop_csv}")
    print(f"- used_creatives: {creatives.exists()}")
    print(f"- used_canonical: {bool(canonical_csv and canonical_csv.exists())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())