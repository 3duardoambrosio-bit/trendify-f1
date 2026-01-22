from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any


def _slug_ascii(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "product"
    # NFKD -> drop diacritics -> ascii
    s2 = unicodedata.normalize("NFKD", s)
    s2 = s2.encode("ascii", "ignore").decode("ascii")
    # keep alnum, turn others into '-'
    out = []
    for ch in s2.lower():
        out.append(ch if ch.isalnum() else "-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or "product"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_items(dump: Any) -> list[dict[str, Any]]:
    if isinstance(dump, list):
        return [x for x in dump if isinstance(x, dict)]

    if isinstance(dump, dict):
        for k in ("items", "results", "candidates", "data", "products"):
            v = dump.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]

        # Sometimes it's a dict keyed by id
        vals = list(dump.values())
        if vals and all(isinstance(v, dict) for v in vals):
            return vals  # type: ignore[return-value]

    return []


def _pid_from_item(it: dict[str, Any]) -> str:
    for k in ("product_id", "id", "sku", "productId", "productID"):
        v = it.get(k)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return ""


def _title_from_item(it: dict[str, Any], fallback: str) -> str:
    for k in ("title", "name", "product_name", "productName"):
        v = it.get(k)
        if v:
            s = str(v).strip()
            if s:
                return s
    return fallback


def _desc_from_item(it: dict[str, Any]) -> str:
    for k in ("description", "desc", "body", "product_description"):
        v = it.get(k)
        if v:
            s = str(v).strip()
            if s:
                return s
    return ""


def load_shortlist_ids(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"shortlist not found: {path}")
    ids: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            raise ValueError("shortlist csv has no header")
        # Try common columns
        cols = [c for c in ("product_id", "id") if c in r.fieldnames]
        if not cols:
            # fallback: first column
            cols = [r.fieldnames[0]]
        col = cols[0]
        for row in r:
            v = (row.get(col) or "").strip()
            if v:
                ids.append(v)
    # de-dup preserving order
    seen = set()
    out = []
    for x in ids:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    shortlist = Path(args.shortlist)
    dump_path = Path(args.dump)
    out_path = Path(args.out)

    if not dump_path.exists():
        print(f"ERROR: dump not found: {dump_path}", file=sys.stderr)
        return 2

    ids = load_shortlist_ids(shortlist)
    if not ids:
        print("ERROR: shortlist produced 0 product ids", file=sys.stderr)
        return 3

    dump = _load_json(dump_path)
    items = _extract_items(dump)

    by_id: dict[str, dict[str, Any]] = {}
    for it in items:
        pid = _pid_from_item(it)
        if pid and pid not in by_id:
            by_id[pid] = it

    rows: list[dict[str, str]] = []
    for pid in ids:
        it = by_id.get(pid, {})
        title = _title_from_item(it, fallback=pid)
        desc = _desc_from_item(it)
        handle = str(it.get("handle") or "").strip()
        if not handle:
            handle = _slug_ascii(title)

        rows.append(
            {
                "product_id": pid,
                "title": title,
                "description": desc,
                "handle": _slug_ascii(handle),  # enforce ascii slug always
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=["product_id", "title", "description", "handle"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # hard guarantee
    if not out_path.exists() or out_path.stat().st_size < 10:
        print(f"ERROR: wrote nothing to out: {out_path}", file=sys.stderr)
        return 4

    print("build_canonical_from_dropi: OK")
    print(f"- out: {out_path}")
    print(f"- rows: {len(rows)}")
    print(f"- first: {rows[0]['product_id'] if rows else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())