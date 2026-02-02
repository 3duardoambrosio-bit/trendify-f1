from infra.time_utils import now_utc

﻿#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dropi_enrich_dump_with_catalog.py
- Enriquecer dump (v2 items[] o v3 candidates[]) usando un catálogo CSV.
- Auto-detect encoding/delimiter.
- Auto-mapea headers del CSV a schema canónico.
- Output: dump v3 con candidates[].source dict completo.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
from typing import Dict, List, Optional, Tuple


CANON_KEYS = ["product_id", "title", "description", "price", "compare_at_price", "image_url", "tags"]

SYNONYMS: Dict[str, List[str]] = {
    "product_id": [
        "product_id", "productid", "id", "producto_id", "producto", "product", "sku", "product_sku",
        "variant_sku", "codigo", "código", "codigo_producto", "codigo_de_producto", "code", "item_id"
    ],
    "title": [
        "title", "name", "product_name", "nombre", "nombre_producto", "producto", "titulo", "título",
        "product_title"
    ],
    "description": [
        "description", "desc", "body", "body_html", "descripcion", "descripción", "detalle", "details",
        "long_description", "short_description", "product_description"
    ],
    "price": [
        "price", "precio", "sale_price", "precio_venta", "unit_price", "price_mxn", "mxn_price", "amount"
    ],
    "compare_at_price": [
        "compare_at_price", "compareatprice", "old_price", "precio_lista", "precio_regular",
        "precio_original", "precio_normal", "regular_price", "list_price"
    ],
    "image_url": [
        "image_url", "image", "img", "imagen", "imagen_url", "url_imagen", "foto", "photo",
        "thumbnail", "main_image", "featured_image", "images", "imagenes"
    ],
    "tags": [
        "tags", "etiquetas", "categories", "category", "categoria", "categoría", "collections", "collection"
    ],
}


def _now_iso() -> str:
    return _dt.now_utc().replace(microsecond=0).isoformat().replace("+00:00","Z")


def _norm_header(h: str) -> str:
    h = (h or "").strip().lower()
    h = h.replace("\ufeff", "")
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
        candidates = [",", ";", "\t", "|"]
        counts = [(d, sample.count(d)) for d in candidates]
        counts.sort(key=lambda x: x[1], reverse=True)
        return counts[0][0] if counts and counts[0][1] > 0 else ","


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
        if v <= 0:
            return None
        return v
    except Exception:
        return None


def _extract_first_url(raw: str) -> str:
    s = _clean_text(raw)
    if not s:
        return ""
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list) and arr:
                return _clean_text(arr[0])
        except Exception:
            pass
    for sep in ("|", ";", ",", "\n"):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if parts:
                return parts[0]
    return s.strip()


def _split_tags(raw: str) -> List[str]:
    s = _clean_text(raw)
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                out = []
                for x in arr:
                    t = _clean_text(x)
                    if t:
                        out.append(t)
                return _dedupe_preserve(out)
        except Exception:
            pass
    for sep in ("|", ";", ","):
        if sep in s:
            toks = [t.strip() for t in s.split(sep) if t.strip()]
            return _dedupe_preserve(toks)
    return [s]


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


def pick_header_map(headers: List[str]) -> Dict[str, Optional[str]]:
    norm_to_orig = {_norm_header(h): h for h in headers}
    norm_headers = list(norm_to_orig.keys())

    mapping: Dict[str, Optional[str]] = {k: None for k in CANON_KEYS}
    for canon_key, syns in SYNONYMS.items():
        for syn in syns:
            syn_n = _norm_header(syn)
            if syn_n in norm_to_orig:
                mapping[canon_key] = norm_to_orig[syn_n]
                break

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


def read_catalog_index(path: str, encoding: str, delimiter: Optional[str]) -> Tuple[Dict[str, dict], Dict[str, dict], Dict[str, Optional[str]], str]:
    with open(path, "r", encoding=encoding, newline="") as f:
        sample = f.read(16384)
        f.seek(0)
        used_delim = delimiter or detect_delimiter(sample)
        reader = csv.DictReader(f, delimiter=used_delim)
        headers = reader.fieldnames or []
        if not headers:
            raise SystemExit("ERROR: catálogo CSV sin headers (fieldnames vacíos).")

        header_map = pick_header_map(headers)

        by_id: Dict[str, dict] = {}
        by_title: Dict[str, dict] = {}

        for i, row in enumerate(reader, start=1):
            pid_h = header_map.get("product_id")
            title_h = header_map.get("title")
            desc_h = header_map.get("description")
            price_h = header_map.get("price")
            cap_h = header_map.get("compare_at_price")
            img_h = header_map.get("image_url")
            tags_h = header_map.get("tags")

            pid = _clean_text(row.get(pid_h)) if pid_h else ""
            title = _clean_text(row.get(title_h)) if title_h else ""
            desc = _clean_text(row.get(desc_h)) if desc_h else ""
            price = _parse_price(row.get(price_h)) if price_h else None
            cap = _parse_price(row.get(cap_h)) if cap_h else None
            img = _extract_first_url(row.get(img_h) if img_h else "")
            tags = _split_tags(row.get(tags_h) if tags_h else "")

            if not title:
                title = f"Dropi Product {i}"

            if not pid:
                slug = re.sub(r"[^\w]+", "-", title.strip().lower(), flags=re.UNICODE).strip("-")
                slug = slug[:40] if slug else "dropi"
                pid = f"{slug}-{i}"

            if not desc:
                base = title
                if tags:
                    base += f". Tags: {', '.join(tags[:8])}"
                desc = base + ". Producto de catálogo Dropi."

            record = {
                "product_id": pid,
                "title": title,
                "description": desc,
                "price": price,
                "compare_at_price": cap,
                "image_url": img,
                "tags": tags,
            }

            if pid and pid not in by_id:
                by_id[pid] = record
            tkey = title.strip().lower()
            if tkey and tkey not in by_title:
                by_title[tkey] = record

        return by_id, by_title, header_map, used_delim


def load_dump(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_candidates_list(d: dict) -> Tuple[List[dict], str]:
    if isinstance(d, dict) and "candidates" in d and isinstance(d["candidates"], list):
        return d["candidates"], "candidates"
    if isinstance(d, dict) and "items" in d and isinstance(d["items"], list):
        return d["items"], "items"
    raise SystemExit("ERROR: dump JSON no tiene 'candidates' ni 'items' como lista.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--encoding", default="")
    ap.add_argument("--delimiter", default="")
    args = ap.parse_args()

    enc = args.encoding.strip() or detect_encoding(args.catalog)
    delim = args.delimiter.strip() or None

    catalog_by_id, catalog_by_title, header_map, used_delim = read_catalog_index(args.catalog, enc, delim)
    d = load_dump(args.dump)
    items, items_key = dump_candidates_list(d)

    enriched = []
    matched_id = 0
    matched_title = 0
    missing_both = 0

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue

        pid = _clean_text(item.get("product_id"))
        title = _clean_text(item.get("title"))

        src = item.get("source")
        if not isinstance(src, dict):
            src = {}

        if not pid:
            pid = _clean_text(src.get("product_id"))
        if not title:
            title = _clean_text(src.get("title"))

        rec = None
        if pid and pid in catalog_by_id:
            rec = catalog_by_id[pid]
            matched_id += 1
        else:
            tkey = title.strip().lower() if title else ""
            if tkey and tkey in catalog_by_title:
                rec = catalog_by_title[tkey]
                matched_title += 1

        if rec is None:
            missing_both += 1
            if not pid:
                pid = f"unknown-{idx}"
            if not title:
                title = f"Unknown Product {idx}"
            if not src.get("description"):
                src["description"] = f"{title}. Producto sin match en catálogo."
            src.setdefault("product_id", pid)
            src.setdefault("title", title)
            item_out = dict(item)
            item_out["product_id"] = pid
            item_out["title"] = title
            item_out["source"] = src
            item_out.setdefault("score", float(item_out.get("score", 0.0) or 0.0))
            enriched.append(item_out)
            continue

        src_out = dict(src)
        for k in CANON_KEYS:
            v = rec.get(k)
            if k == "tags":
                existing = src_out.get("tags")
                existing_list = existing if isinstance(existing, list) else []
                merged = existing_list + (v or [])
                src_out["tags"] = list(dict.fromkeys([str(x) for x in merged if str(x).strip()]))
                continue

            if k in ("price", "compare_at_price"):
                if src_out.get(k) is None and v is not None:
                    src_out[k] = v
                continue

            if not _clean_text(src_out.get(k)):
                if v is not None:
                    src_out[k] = v

        item_out = dict(item)
        item_out["product_id"] = rec.get("product_id") or pid or item_out.get("product_id") or f"unknown-{idx}"
        item_out["title"] = rec.get("title") or title or item_out.get("title") or f"Unknown Product {idx}"
        item_out["source"] = src_out
        item_out.setdefault("score", float(item_out.get("score", 0.0) or 0.0))
        enriched.append(item_out)

    out = dict(d)
    out.pop("items", None)
    out.pop("candidates", None)
    out["schema_version"] = "dropi_dump_v3"
    out["generated_at"] = _now_iso()
    out["enriched_from_catalog"] = {
        "catalog_path": args.catalog,
        "encoding": enc,
        "delimiter": used_delim,
        "mapping": header_map,
        "matched_by_id": matched_id,
        "matched_by_title": matched_title,
        "unmatched": missing_both,
        "input_key": items_key,
        "input_count": len(items),
        "output_count": len(enriched),
    }
    out["candidates"] = enriched

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("dropi_enrich_dump_with_catalog: OK")
    print(f"- out: {args.out}")
    print(f"- matched_by_id: {matched_id}  matched_by_title: {matched_title}  unmatched: {missing_both}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
