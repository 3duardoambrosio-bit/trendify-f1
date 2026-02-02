from infra.time_utils import now_utc

﻿#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dropi_catalog_ingest.py
CSV real -> dump v3 (candidates[] con source{} completo + score).

Robusto:
- detecta encoding/delimitador
- auto-mapea headers
- parsea precio
- extrae 1er image_url REAL (ignora placeholders y urls chafas)

Uso:
  python scripts/dropi_catalog_ingest.py --catalog data\\evidence\\dropi_catalog_export_REAL.csv --out data\\evidence\\launch_candidates_dropi_catalog_v3.json --limit 5000
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


CANON_KEYS = ["product_id", "title", "description", "price", "compare_at_price", "image_url", "tags"]

SYNONYMS: Dict[str, List[str]] = {
    "product_id": ["product_id","productid","id","sku","product_sku","variant_sku","item_id","codigo","código","code","producto_id"],
    "title": ["title","name","product_name","nombre","nombre_producto","titulo","título","product_title"],
    "description": ["description","desc","body","body_html","descripcion","descripción","detalle","details","long_description","short_description"],
    "price": ["price","precio","sale_price","precio_venta","unit_price","amount","price_mxn","mxn_price"],
    "compare_at_price": ["compare_at_price","compareatprice","old_price","precio_lista","precio_regular","regular_price","list_price"],
    "image_url": ["image_url","image","img","imagen","imagen_url","url_imagen","photo","thumbnail","main_image","featured_image","images","imagenes"],
    "tags": ["tags","etiquetas","categories","category","categoria","categoría","collections","collection"],
}

# Bloqueo de placeholders (puedes ampliar cuando veas otros)
BLOCKED_IMAGE_PATTERNS = [
    re.compile(r"via\.placeholder\.com", re.IGNORECASE),
    re.compile(r"placehold\.it", re.IGNORECASE),
    re.compile(r"dummyimage\.com", re.IGNORECASE),
    re.compile(r"picsum\.photos", re.IGNORECASE),
]

URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _now_iso() -> str:
    return _dt.now_utc().replace(microsecond=0).isoformat().replace("+00:00","Z")


def _norm_header(h: str) -> str:
    h = (h or "").strip().lower().replace("\ufeff", "")
    h = re.sub(r"[^\w]+", "_", h, flags=re.UNICODE)
    h = re.sub(r"_+", "_", h).strip("_")
    return h


def _try_decode(path: str, enc: str) -> bool:
    try:
        with open(path, "r", encoding=enc, newline="") as f:
            f.read(4096)
        return True
    except Exception:
        return False


def detect_encoding(path: str) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        if _try_decode(path, enc):
            return enc
    return "utf-8-sig"


def detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        ds = [",", ";", "\t", "|"]
        best = max(ds, key=lambda d: sample.count(d))
        return best if sample.count(best) > 0 else ","


def _clean_text(x: Optional[str]) -> str:
    if x is None:
        return ""
    return str(x).replace("\r\n", "\n").strip()


def _parse_price(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s or s in ("-", ".", ","):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
        return v if v > 0 else None
    except Exception:
        return None


def _is_url(s: str) -> bool:
    return bool(URL_RE.match((s or "").strip()))


def _is_blocked_image_url(s: str) -> bool:
    if not s:
        return False
    for pat in BLOCKED_IMAGE_PATTERNS:
        if pat.search(s):
            return True
    return False


def _extract_image_candidates(raw: str) -> List[str]:
    s = _clean_text(raw)
    if not s:
        return []

    # JSON list string
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [_clean_text(x) for x in arr if _clean_text(x)]
        except Exception:
            pass

    # Separadores típicos
    for sep in ("|", "; ", ",", "\n"):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            return parts

    return [s.strip()]


def _extract_first_real_image_url(raw: str, block_placeholders: bool = True) -> Tuple[str, int]:
    """
    Regresa (url, blocked_hits)
    - Se queda con la primera URL http(s) válida
    - Si block_placeholders=True, ignora placeholders y los cuenta
    """
    blocked_hits = 0
    candidates = _extract_image_candidates(raw)

    for u in candidates:
        if not _is_url(u):
            continue
        if block_placeholders and _is_blocked_image_url(u):
            blocked_hits += 1
            continue
        return u, blocked_hits

    # si todas eran placeholders, igual cuenta y regresa vacío
    if block_placeholders:
        for u in candidates:
            if _is_url(u) and _is_blocked_image_url(u):
                # ya los contamos arriba si eran URLs; esto es por si hubo rarezas
                pass
    return "", blocked_hits


def _dedupe_preserve(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        k = x.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x.strip())
    return out


def _split_tags(raw: str) -> List[str]:
    s = _clean_text(raw)
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return _dedupe_preserve([_clean_text(x) for x in arr if _clean_text(x)])
        except Exception:
            pass
    for sep in ("|", "; ", ","):
        if sep in s:
            return _dedupe_preserve([t.strip() for t in s.split(sep) if t.strip()])
    return [s]


def pick_header_map(headers: List[str]) -> Dict[str, Optional[str]]:
    norm_to_orig = {_norm_header(h): h for h in headers}
    norm_headers = list(norm_to_orig.keys())

    mapping: Dict[str, Optional[str]] = {k: None for k in CANON_KEYS}
    for canon_key, syns in SYNONYMS.items():
        for syn in syns:
            sn = _norm_header(syn)
            if sn in norm_to_orig:
                mapping[canon_key] = norm_to_orig[sn]
                break

    # fallbacks
    if mapping["title"] is None:
        for nh in norm_headers:
            if "name" in nh or "nombre" in nh or "titulo" in nh or "title" in nh:
                mapping["title"] = norm_to_orig[nh]
                break

    if mapping["product_id"] is None:
        for nh in norm_headers:
            if nh in ("id", "sku") or nh.endswith("_id") or "product_id" in nh:
                mapping["product_id"] = norm_to_orig[nh]
                break

    if mapping["image_url"] is None:
        for nh in norm_headers:
            if "image" in nh or "img" in nh or "imagen" in nh or ("url" in nh and ("img" in nh or "image" in nh or "imagen" in nh)):
                mapping["image_url"] = norm_to_orig[nh]
                break

    if mapping["price"] is None:
        for nh in norm_headers:
            if "price" in nh or "precio" in nh:
                mapping["price"] = norm_to_orig[nh]
                break

    if mapping["description"] is None:
        for nh in norm_headers:
            if "desc" in nh or "description" in nh or "descripcion" in nh or "detalle" in nh:
                mapping["description"] = norm_to_orig[nh]
                break

    if mapping["tags"] is None:
        for nh in norm_headers:
            if "tag" in nh or "etiquet" in nh or "categor" in nh or "collection" in nh:
                mapping["tags"] = norm_to_orig[nh]
                break

    return mapping


@dataclass
class CanonRow:
    product_id: str
    title: str
    description: str
    price: Optional[float]
    compare_at_price: Optional[float]
    image_url: str
    tags: List[str]
    image_blocked_hits: int = 0


def canonize_row(row: Dict[str, str], hm: Dict[str, Optional[str]], idx: int, block_placeholders: bool) -> CanonRow:
    def getv(k: str) -> str:
        h = hm.get(k)
        return _clean_text(row.get(h)) if h else ""

    pid = getv("product_id")
    title = getv("title") or f"Dropi Product {idx}"
    desc = getv("description")
    price = _parse_price(getv("price"))
    cap = _parse_price(getv("compare_at_price"))

    img_raw = getv("image_url")
    img, blocked_hits = _extract_first_real_image_url(img_raw, block_placeholders=block_placeholders)

    tags = _split_tags(getv("tags"))

    if not pid:
        slug = re.sub(r"[^\w]+", "-", title.strip().lower(), flags=re.UNICODE).strip("-")
        slug = slug[:40] if slug else "dropi"
        pid = f"{slug}-{idx}"

    if not desc:
        base = title + (f". Tags: {', '.join(tags[:8])}" if tags else "")
        desc = base + ". Producto de catálogo Dropi."

    return CanonRow(pid, title, desc, price, cap, img, tags, blocked_hits)


def score_row(c: CanonRow, price_min: float, price_max: float) -> float:
    s = 0.0
    if c.price is not None:
        s += 2.0
        if price_min <= c.price <= price_max:
            s += 1.0
    if c.image_url:
        s += 2.0
    if c.description and len(c.description) >= 60:
        s += 1.0
    if c.tags:
        s += 0.5
    if c.compare_at_price is not None and c.price is not None and c.compare_at_price > c.price:
        s += 0.5
    return float(s)


def read_catalog_rows(path: str, enc: str, delimiter: Optional[str], limit: int) -> Tuple[List[Dict[str, str]], List[str], str]:
    with open(path, "r", encoding=enc, newline="") as f:
        sample = f.read(16384)
        f.seek(0)
        used = delimiter or detect_delimiter(sample)
        reader = csv.DictReader(f, delimiter=used)
        headers = reader.fieldnames or []
        rows: List[Dict[str, str]] = []
        for r in reader:
            rows.append(r)
            if limit > 0 and len(rows) >= limit:
                break
        return rows, headers, used


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--encoding", default="")
    ap.add_argument("--delimiter", default="")
    ap.add_argument("--price-min", type=float, default=12.0)
    ap.add_argument("--price-max", type=float, default=70.0)
    ap.add_argument("--no-require-price", action="store_true")
    ap.add_argument("--no-require-image", action="store_true")

    # NUEVO: control de placeholders
    ap.add_argument("--allow-placeholder-images", action="store_true",
                    help="Permite URLs placeholder (NO recomendado). Default: bloquea placeholders.")
    args = ap.parse_args()

    require_price = not args.no_require_price
    require_image = not args.no_require_image
    block_placeholders = not args.allow_placeholder_images

    enc = args.encoding.strip() or detect_encoding(args.catalog)
    delim = args.delimiter.strip() or None

    rows, headers, used_delim = read_catalog_rows(args.catalog, enc, delim, int(args.limit))
    if not headers:
        raise SystemExit("ERROR: CSV sin headers (fieldnames vacíos). Revisa export/delimitador/encoding.")

    hm = pick_header_map(headers)

    print("dropi_catalog_ingest: OK")
    print(f"- catalog: {args.catalog}")
    print(f"- encoding: {enc}")
    print(f"- delimiter: {repr(used_delim)}")
    print(f"- rows_read: {len(rows)}")
    print(f"- require_price: {require_price}")
    print(f"- require_image: {require_image}")
    print(f"- block_placeholders: {block_placeholders}")
    print("- MAPPING:")
    for k in CANON_KEYS:
        print(f"  {k}: {hm.get(k)}")

    kept = 0
    skipped_price = 0
    skipped_image = 0
    skipped_image_placeholder = 0
    placeholder_blocked_total = 0
    placeholder_rows = 0

    seen = set()
    candidates = []

    for i, r in enumerate(rows, start=1):
        c = canonize_row(r, hm, i, block_placeholders=block_placeholders)

        if c.image_blocked_hits > 0:
            placeholder_blocked_total += c.image_blocked_hits
            placeholder_rows += 1

        if require_price and c.price is None:
            skipped_price += 1
            continue

        if require_image and not c.image_url:
            skipped_image += 1
            if c.image_blocked_hits > 0:
                skipped_image_placeholder += 1
            continue

        pid = c.product_id
        if pid in seen:
            pid = f"{pid}-{i}"
            c = CanonRow(pid, c.title, c.description, c.price, c.compare_at_price, c.image_url, c.tags, c.image_blocked_hits)
        seen.add(pid)

        sc = score_row(c, args.price_min, args.price_max)
        candidates.append({
            "product_id": c.product_id,
            "title": c.title,
            "score": sc,
            "source": {
                "product_id": c.product_id,
                "title": c.title,
                "description": c.description,
                "price": c.price,
                "compare_at_price": c.compare_at_price,
                "image_url": c.image_url,
                "tags": c.tags,
            },
        })
        kept += 1

    candidates.sort(key=lambda x: (-float(x.get("score", 0.0)), str(x.get("product_id", ""))))

    out = {
        "schema_version": "dropi_dump_v3",
        "generated_at": _now_iso(),
        "catalog_ingest": {
            "catalog_path": args.catalog,
            "encoding": enc,
            "delimiter": used_delim,
            "limit": int(args.limit),
            "require_price": require_price,
            "require_image": require_image,
            "block_placeholders": block_placeholders,
            "blocked_patterns": [p.pattern for p in BLOCKED_IMAGE_PATTERNS] if block_placeholders else [],
            "skipped_price": skipped_price,
            "skipped_image": skipped_image,
            "skipped_image_placeholder": skipped_image_placeholder,
            "rows_read": len(rows),
            "kept": kept,
            "mapping": hm,
            "placeholder_rows_with_hits": placeholder_rows,
            "placeholder_blocked_total": placeholder_blocked_total,
        },
        "candidates": candidates,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("- SUMMARY:")
    print(f"  kept={kept} skipped_price={skipped_price} skipped_image={skipped_image} skipped_image_placeholder={skipped_image_placeholder}")
    print(f"  placeholders: rows_with_hits={placeholder_rows} blocked_total={placeholder_blocked_total}")
    print(f"- out: {args.out}")
    if kept == 0:
        print("WARNING: kept=0 (normalmente: price no parsea o image_url real no existe; si estás bootstrap, corre con --no-require-image).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
