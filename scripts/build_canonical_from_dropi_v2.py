#!/usr/bin/env python3
"""
build_canonical_from_dropi_v2.py

Construye canonical_products.csv a partir de:
- shortlist.csv (debe tener columna: product_id)
- dump.json (Dropi candidates dump)

Soporta schemas:
- v2: candidates con source None / string (no hay catálogo embebido)
- v3: candidates con source dict (catálogo embebido: price, image_url, description, tags, etc.)

Salida:
- canonical_products.csv (CSV)
- canonical_products.report.json (JSON) en el MISMO directorio que --out
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
    Si no, devuelve ''.
    """
    if x is None:
        return ""
    if isinstance(x, (int, float)):
        return f"{float(x):.2f}"
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return ""
        # intenta parsear aunque venga con $ o comas
        s2 = s.replace("$", "").replace(",", "").strip()
        try:
            return f"{float(s2):.2f}"
        except Exception:
            return s  # si no parsea, lo dejamos tal cual (mejor que borrar)
    return _to_str(x)


def _split_tags(tags: Any) -> str:
    """
    Canonical: guardamos tags como string CSV 'a,b,c'.
    Si viene lista, la unimos. Si viene string, la normalizamos.
    """
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

    # dedupe manteniendo orden
    seen = set()
    out = []
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
    source_raw: Any  # puede ser dict (v3), string/None (v2)


def _extract_candidates(dump: Any) -> List[Candidate]:
    if not isinstance(dump, dict):
        return []

    cand_list: List[Dict[str, Any]] = []
    if isinstance(dump.get("candidates"), list):
        cand_list.extend(dump["candidates"])

    # a veces 'top' trae objetos parecidos; lo metemos también por si acaso
    if isinstance(dump.get("top"), list):
        cand_list.extend(dump["top"])

    out: List[Candidate] = []
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
    Si hay duplicados, nos quedamos con el de mayor score (si existe),
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
            # aun así emitimos fila (no queremos romper pipeline)
            row = {
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
            rows.append(row)
            continue

        src = _source_dict(c.source_raw)

        title = _to_str(src.get("title")) or c.title
        desc = _to_str(src.get("description"))
        price = _to_float_str(src.get("price"))
        cap = _to_float_str(src.get("compare_at_price"))
        img = _to_str(src.get("image_url"))
        tags = _split_tags(src.get("tags"))

        # counters
        if price:
            fill_price += 1
        if img:
            fill_image += 1
        if desc:
            fill_desc += 1

        row = {
            "product_id": pid,
            "title": title,
            "description": desc,
            "price": price,
            "compare_at_price": cap,
            "image_url": img,
            "tags": tags,
            "score": "" if c.score is None else _to_str(c.score),
            "reason": c.reason,
            "source_name": "embedded_catalog" if isinstance(c.source_raw, dict) else _to_str(c.source_raw),
            "source_payload_json": "" if not isinstance(c.source_raw, dict) else json.dumps(c.source_raw, ensure_ascii=False),
        }
        rows.append(row)

    report = {
        "ts_utc": _now_utc_iso(),
        "shortlist_total": len(shortlist_ids),
        "rows": len(rows),
        "missing_from_dump": missing,
        "fill_price": f"{fill_price}/{len(rows) if rows else 0}",
        "fill_image": f"{fill_image}/{len(rows) if rows else 0}",
        "fill_desc": f"{fill_desc}/{len(rows) if rows else 0}",
        "rates": {
            "price": (fill_price / len(rows)) if rows else 0.0,
            "image": (fill_image / len(rows)) if rows else 0.0,
            "desc": (fill_desc / len(rows)) if rows else 0.0,
        },
    }
    return rows, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist", required=True, help="Path to shortlist.csv (must include product_id)")
    ap.add_argument("--dump", required=True, help="Path to Dropi dump json (v2/v3)")
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

    # Log estilo “pipeline”
    print("build_canonical_from_dropi_v2: OK")
    print(f"- out: {out_p}")
    print(f"- rows: {len(rows)}")
    print(f"- report: {report_p}")
    # imprime contadores como tu output actual
    print(f"- fill_price: {report['fill_price']}")
    print(f"- fill_image: {report['fill_image']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
