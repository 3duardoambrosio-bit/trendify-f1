#!/usr/bin/env python3
"""
build_canonical_from_dropi_v2.py

Construye canonical_products.csv a partir de:
- shortlist.csv (debe tener columna: product_id)
- dump.json (Dropi candidates dump)

Soporta schemas:
A) v2/v3 "candidates"/"top": lista de dicts con product_id/title/score/reason/source
   - source puede ser None/string (v2)
   - source puede ser dict con {price,image_url,description,tags,...} (v3 enriquecido)
B) legacy "items": lista de productos (usado por tests)
   - id -> product_id
   - images[0].url -> image_url
   - price/compare_at_price pueden venir como "$29.99"

Salida:
- canonical CSV (path --out)
- canonical_products.report.json en el MISMO directorio que --out
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _load_json(p: Path) -> Any:
    return json.loads(_read_text(p))


def _to_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def _to_float_str(x: Any) -> str:
    """
    Normaliza precio a string tipo '29.99' si es posible.
    Si no, devuelve '' (o el string original si no parsea pero existe).
    """
    if x is None:
        return ""
    if isinstance(x, (int, float)):
        return f"{float(x):.2f}"
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return ""
        s2 = s.replace("$", "").replace(",", "").strip()
        try:
            return f"{float(s2):.2f}"
        except Exception:
            return s
    return _to_str(x)


def _split_tags(tags: Any) -> str:
    if tags is None:
        return ""
    if isinstance(tags, list):
        return ",".join([_to_str(t) for t in tags if _to_str(t)])
    return _to_str(tags)


def _read_shortlist_ids(shortlist_csv: Path) -> List[str]:
    if not shortlist_csv.exists():
        raise FileNotFoundError(f"shortlist not found: {shortlist_csv}")

    rows = list(csv.DictReader(open(shortlist_csv, encoding="utf-8", newline="")))
    if not rows:
        raise SystemExit("shortlist.csv has no rows")

    ids: List[str] = []
    for r in rows:
        pid = _to_str(r.get("product_id"))
        if pid:
            ids.append(pid)

    if not ids:
        raise SystemExit("shortlist.csv missing product_id values")

    seen = set()
    out: List[str] = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


@dataclass
class Candidate:
    product_id: str
    title: str
    score: Optional[float]
    reason: str
    source_raw: Any  # dict (v3 o legacy-normalizado) o string/None (v2)


def _first_image_url(item: Dict[str, Any]) -> str:
    # v3/legacy: images: [{url:...}] / [{src:...}] / [{link:...}]
    imgs = item.get("images")
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, dict):
            for k in ("url", "src", "link", "href"):
                u = _to_str(first.get(k))
                if u:
                    return u
    # a veces ya viene directo
    for k in ("image_url", "image", "img", "photo_url", "primary_image_url"):
        u = _to_str(item.get(k))
        if u:
            return u
    return ""


def _extract_candidates_from_items(dump: Dict[str, Any]) -> List[Candidate]:
    """
    Soporte legacy: dump = {"items":[{id,title,description,price,...}]}
    Convertimos cada item a Candidate con source_raw dict NORMALIZADO a llaves canonical.
    """
    items = dump.get("items")
    if not isinstance(items, list):
        return []

    out: List[Candidate] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        pid = _to_str(it.get("product_id") or it.get("id"))
        if not pid:
            continue

        title = _to_str(it.get("title"))
        src_norm = {
            "product_id": pid,
            "title": title,
            "description": _to_str(it.get("description")),
            "price": it.get("price"),
            "compare_at_price": it.get("compare_at_price"),
            "image_url": _first_image_url(it),
            "tags": it.get("tags"),
        }

        score_val = it.get("score")
        score: Optional[float] = None
        try:
            if score_val is not None and _to_str(score_val):
                score = float(score_val)
        except Exception:
            score = None

        out.append(
            Candidate(
                product_id=pid,
                title=title,
                score=score,
                reason=_to_str(it.get("reason")),
                source_raw=src_norm,  # dict para que el builder lo tome como "embedded"
            )
        )
    return out


def _extract_candidates(dump: Any) -> List[Candidate]:
    if not isinstance(dump, dict):
        return []

    out: List[Candidate] = []

    # B) legacy items
    out.extend(_extract_candidates_from_items(dump))

    # A) candidates/top
    cand_list: List[Any] = []
    if isinstance(dump.get("candidates"), list):
        cand_list.extend(dump["candidates"])
    if isinstance(dump.get("top"), list):
        cand_list.extend(dump["top"])

    for c in cand_list:
        if not isinstance(c, dict):
            continue
        pid = _to_str(c.get("product_id"))
        if not pid:
            continue

        title = _to_str(c.get("title"))
        reason = _to_str(c.get("reason"))

        score_val = c.get("score")
        score: Optional[float] = None
        try:
            if score_val is not None and _to_str(score_val):
                score = float(score_val)
        except Exception:
            score = None

        out.append(
            Candidate(
                product_id=pid,
                title=title,
                score=score,
                reason=reason,
                source_raw=c.get("source"),
            )
        )

    return out


def _index_candidates(cands: List[Candidate]) -> Dict[str, Candidate]:
    """
    Duplicados: nos quedamos con el de mayor score (si existe),
    si no, el primero.
    """
    idx: Dict[str, Candidate] = {}
    for c in cands:
        if c.product_id not in idx:
            idx[c.product_id] = c
            continue

        prev = idx[c.product_id]
        if prev.score is None and c.score is not None:
            idx[c.product_id] = c
            continue
        if prev.score is not None and c.score is None:
            continue
        if prev.score is not None and c.score is not None and c.score > prev.score:
            idx[c.product_id] = c
    return idx


def _source_dict(source_raw: Any) -> Dict[str, Any]:
    return source_raw if isinstance(source_raw, dict) else {}


def build_canonical_rows(shortlist_ids: List[str], dump: Any) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    cands = _extract_candidates(dump)
    idx = _index_candidates(cands)

    rows: List[Dict[str, str]] = []
    missing: List[str] = []

    fill_price = 0
    fill_image = 0
    fill_desc = 0

    for pid in shortlist_ids:
        c = idx.get(pid)
        if c is None:
            missing.append(pid)
            rows.append(
                {
                    "product_id": pid,
                    "title": "",
                    "description": "",
                    "price": "",
                    "compare_at_price": "",
                    "image_url": "",
                    "tags": "",
                    "score": "",
                    "reason": "",
                    "source_name": "",
                    "source_payload_json": "",
                }
            )
            continue

        src = _source_dict(c.source_raw)

        title = _to_str(src.get("title")) or c.title
        desc = _to_str(src.get("description"))
        price = _to_float_str(src.get("price"))
        cap = _to_float_str(src.get("compare_at_price"))
        img = _to_str(src.get("image_url"))
        tags = _split_tags(src.get("tags"))

        if price:
            fill_price += 1
        if img:
            fill_image += 1
        if desc:
            fill_desc += 1

        # "source_name": si source_raw era dict, lo tratamos como catálogo embebido
        source_name = "embedded_catalog" if isinstance(c.source_raw, dict) else _to_str(c.source_raw)

        rows.append(
            {
                "product_id": pid,
                "title": title,
                "description": desc,
                "price": price,
                "compare_at_price": cap,
                "image_url": img,
                "tags": tags,
                "score": "" if c.score is None else _to_str(c.score),
                "reason": c.reason,
                "source_name": source_name,
                "source_payload_json": "" if not isinstance(c.source_raw, dict) else json.dumps(c.source_raw, ensure_ascii=False),
            }
        )

    total = len(rows) if rows else 0
    report = {
        "ts_utc": _now_utc_iso(),
        "shortlist_total": len(shortlist_ids),
        "rows": len(rows),
        "missing_from_dump": missing,
        "fill_price": f"{fill_price}/{total}",
        "fill_image": f"{fill_image}/{total}",
        "fill_desc": f"{fill_desc}/{total}",
        "rates": {
            "price": (fill_price / total) if total else 0.0,
            "image": (fill_image / total) if total else 0.0,
            "desc": (fill_desc / total) if total else 0.0,
        },
    }
    return rows, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True, help="Path to shortlist.csv (must include product_id)")
    ap.add_argument("--dump", required=True, help="Path to Dropi dump json (v2/v3/items)")
    ap.add_argument("--out", required=True, help="Path to canonical_products.csv")
    args = ap.parse_args()

    shortlist_p = Path(args.shortlist)
    dump_p = Path(args.dump)
    out_p = Path(args.out)

    if not dump_p.exists():
        print(f"ERROR: dump not found: {dump_p}", file=sys.stderr)
        return 2

    shortlist_ids = _read_shortlist_ids(shortlist_p)
    dump = _load_json(dump_p)

    rows, report = build_canonical_rows(shortlist_ids, dump)

    out_p.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "product_id",
        "title",
        "description",
        "price",
        "compare_at_price",
        "image_url",
        "tags",
        "score",
        "reason",
        "source_name",
        "source_payload_json",
    ]

    with open(out_p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    report_p = out_p.parent / "canonical_products.report.json"
    report_p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("build_canonical_from_dropi_v2: OK")
    print(f"- out: {out_p}")
    print(f"- rows: {len(rows)}")
    print(f"- report: {report_p}")
    print(f"- fill_price: {report['fill_price']}")
    print(f"- fill_image: {report['fill_image']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
