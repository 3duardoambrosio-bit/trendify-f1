from __future__ import annotations

from synapse.infra.cli_logging import cli_print

# ops/dropi_dump_ingest.py
# Ingesta un "dump" JSON (copy-paste de DevTools) y genera:
# 1) NDJSON normalizado para tu pipeline
# 2) evidence JSON con TOP N rankeado (margen + assets + confianza)
#
# Uso típico:
#   $env:PYTHONPATH="."
#   python ops\dropi_dump_ingest.py --dump data\dropi_products_dump.json --out data\catalog\dropi_dump --top 10
#
# Nota: No depende de libs externas. Solo stdlib.


import argparse
import datetime as _dt
import json
import os
from pathlib import Path
from urllib.parse import quote


# ----------------------------
# Helpers
# ----------------------------
def _now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _to_decimal(x):
    try:
        if x is None:
            return None
        # soporta "1,234.56" y "123,45"
        s = str(x).strip().replace(" ", "")
        # si trae coma decimal estilo LATAM
        if s.count(",") == 1 and s.count(".") == 0:
            s = s.replace(",", ".")
        # si trae miles con coma y decimal con punto: 1,234.56
        if s.count(",") >= 1 and s.count(".") == 1:
            s = s.replace(",", "")
        return float(s)
    except Exception:
        return None


def _pick_list(raw):
    """
    Dropi dump puede venir como:
      - dict con keys: objects / data / items / products
      - o directamente list
    """
    if isinstance(raw, dict):
        for k in ("objects", "data", "items", "products"):
            v = raw.get(k)
            if isinstance(v, list):
                return v
    if isinstance(raw, list):
        return raw
    raise RuntimeError("No encontré lista de productos en el dump (busqué objects/data/items/products).")


def _full_img_url(url_s3: str | None) -> str | None:
    if not url_s3:
        return None
    u = str(url_s3).strip()
    if not u:
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u

    # Normalmente viene tipo: mexico/products/ID/archivo con espacios
    # Lo armamos a CDN y escapamos caracteres raros, manteniendo '/'
    base = "https://cdn.dropi.mx/"
    return base + quote(u, safe="/:")  # deja / intacto, escapa espacios, etc.


def _normalize_product(p: dict) -> dict:
    # base
    norm = {
        "source": "dropi_dump",
        "id": p.get("id"),
        "sku": p.get("sku") or "",
        "name": p.get("name") or "",
    }

    # proveedor
    user = p.get("user") if isinstance(p.get("user"), dict) else {}
    norm["provider_id"] = user.get("id")
    norm["provider_name"] = user.get("name") or user.get("store_name") or ""

    # verificado (proxy de confianza)
    verified = False
    cat_user = user.get("category_user") if isinstance(user.get("category_user"), dict) else {}
    nm = (cat_user.get("name") or "").upper()
    ic = (cat_user.get("icon") or "").lower()
    if "VERIF" in nm or ic == "verified":
        verified = True
    norm["verified"] = verified

    # categoría (primera)
    category_name = ""
    cats = p.get("categories")
    if isinstance(cats, list) and cats:
        c0 = cats[0]
        if isinstance(c0, dict):
            category_name = c0.get("name") or ""
        else:
            category_name = str(c0)
    norm["category_name"] = category_name

    # stock (suma warehouses si existe)
    stock = None
    wp = p.get("warehouse_product")
    if isinstance(wp, list) and wp:
        s = 0
        for w in wp:
            if isinstance(w, dict):
                try:
                    s += int(w.get("stock") or 0)
                except Exception:
                    pass
        stock = s
    else:
        # fallback si algún dump trae stock directo
        try:
            stock = int(p.get("stock")) if p.get("stock") is not None else None
        except Exception:
            stock = None
    norm["stock"] = stock

    # precios: Dropi suele usar sale_price (costo) y suggested_price (precio sugerido)
    cost = _to_decimal(p.get("sale_price") or p.get("cost") or p.get("price_cost"))
    price = _to_decimal(p.get("suggested_price") or p.get("price") or p.get("regular_price"))
    norm["cost"] = cost
    norm["price"] = price

    # imágenes: gallery.urlS3 -> norm["images"] como URLs completas
    imgs = []
    gallery = p.get("gallery") or p.get("images") or []
    if isinstance(gallery, list):
        for g in gallery:
            if isinstance(g, dict):
                u = g.get("urlS3") or g.get("url") or g.get("src")
            else:
                u = g
            fu = _full_img_url(u)
            if fu and fu not in imgs:
                imgs.append(fu)
    norm["images"] = imgs

    return norm


def _score(norm: dict) -> tuple[float, float | None, float, float, float]:
    """
    Heurística ACERO simple:
      score = 0.55*margen + 0.25*assets(imágenes) + 0.20*confianza(verificado)
    """
    cost = norm.get("cost")
    price = norm.get("price")

    margin = None
    m_score = 0.0
    if cost is not None and price is not None and price > 0:
        margin = (price - cost) / price
        # clamp 0..1
        if margin < 0:
            margin = 0.0
        if margin > 1:
            margin = 1.0
        m_score = float(margin)

    images = norm.get("images") or []
    a_score = min(1.0, (len(images) / 7.0)) if isinstance(images, list) else 0.0

    trust = 10.0 if norm.get("verified") else 5.0
    t_score = max(0.0, min(1.0, trust / 10.0))

    s = 0.55 * m_score + 0.25 * a_score + 0.20 * t_score
    return float(s), margin, float(m_score), float(a_score), float(t_score)


def _write_ndjson(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ----------------------------
# Main
# ----------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, help="Ruta al dump JSON (ej: data\\dropi_products_dump.json)")
    ap.add_argument("--out", required=True, help="Directorio de salida NDJSON (ej: data\\catalog\\dropi_dump)")
    ap.add_argument("--top", type=int, default=10, help="Cuántos TOP exportar (default 10)")
    ap.add_argument("--min-images", type=int, default=1, help="Mínimo de imágenes para calificar (default 1)")
    ap.add_argument("--evidence", default="data\\evidence\\dropi_dump_top.json", help="Ruta evidence JSON")

    args = ap.parse_args()

    dump_path = Path(args.dump)
    if not dump_path.exists():
        raise FileNotFoundError(f"No existe el dump: {dump_path}")

    raw = json.load(dump_path.open("r", encoding="utf-8"))
    products = _pick_list(raw)

    # Normaliza todo
    normalized = []
    for p in products:
        if isinstance(p, dict):
            normalized.append(_normalize_product(p))

    # Escribe NDJSON
    out_dir = Path(args.out)
    ndjson_path = out_dir / f"dropi_dump_catalog_{_now_stamp()}.ndjson"
    _write_ndjson(ndjson_path, normalized)

    # Rankea y arma TOP
    ranked = []
    for n in normalized:
        imgs = n.get("images") or []
        if args.min_images and (not isinstance(imgs, list) or len(imgs) < args.min_images):
            continue
        s, margin, m_score, a_score, t_score = _score(n)
        item = dict(n)
        item["score"] = s
        item["margin"] = margin
        item["score_components"] = {"m_score": m_score, "a_score": a_score, "t_score": t_score}
        ranked.append(item)

    ranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    top = ranked[: max(0, int(args.top))]

    # Evidence
    evidence_path = Path(args.evidence)
    evidence = {
        "meta": {
            "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "dump": str(dump_path),
            "ndjson_path": str(ndjson_path),
            "total_in_dump": len(products),
            "normalized": len(normalized),
            "ranked_candidates": len(ranked),
            "top_requested": int(args.top),
            "min_images": int(args.min_images),
        },
        "top": top,
    }
    _write_json(evidence_path, evidence)

    # Prints
    cli_print(f"OK ndjson: {ndjson_path}")
    cli_print(f"OK evidence: {evidence_path}")
    cli_print(f"TOP: {len(top)}")

    # Mini resumen
    for i, it in enumerate(top, 1):
        name = it.get("name") or ""
        cat = it.get("category_name") or ""
        margin = it.get("margin")
        imgs = it.get("images") or []
        mtxt = "None" if margin is None else f"{margin:.2f}"
        itxt = len(imgs) if isinstance(imgs, list) else 0
        cli_print(f"{i}. {name} | {cat} | margin={mtxt} | imgs={itxt} | score={it.get('score',0):.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
