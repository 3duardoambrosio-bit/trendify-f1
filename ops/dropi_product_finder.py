from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ops.dropi_client import DropiClient, DropiClientConfig, _cfg_from_env
from ops.ledger_writer import LedgerWriter

def _dec(x: Any) -> Optional[Decimal]:
    if x is None:
        return None
    try:
        if isinstance(x, Decimal):
            return x
        if isinstance(x, (int, float)):
            return Decimal(str(x))
        s = str(x).strip().replace(",", ".")
        if s == "":
            return None
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _mkdir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def _ndjson_write(path: str, rows: Iterable[Dict[str, Any]]) -> int:
    _mkdir(os.path.dirname(path))
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
        f.flush()
        os.fsync(f.fileno())
    return n

def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _date_dir() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")

@dataclass
class FinderArgs:
    page_size: int = 50
    max_products: int = 5000
    categories: List[str] = None
    min_images: int = 3
    min_margin_pct: Decimal = Decimal("0.20")  # 20% proxy using suggested_price if available
    top_n: int = 5
    output_dir: str = "data/catalog/dropi"
    evidence_path: str = "evidence/launch_candidates_dropi.json"

def _normalize_product(p: Dict[str, Any]) -> Dict[str, Any]:
    # Best-effort normalization based on common Dropi fields.
    pid = p.get("id") or p.get("product_id") or p.get("_id")
    title = p.get("name") or p.get("title") or ""
    desc = p.get("description") or ""
    category = p.get("category") or {}
    category_id = category.get("id") if isinstance(category, dict) else p.get("category_id")
    category_name = category.get("name") if isinstance(category, dict) else p.get("category_name")

    cost = _dec(p.get("sale_price") or p.get("cost") or p.get("price_cost"))
    suggested = _dec(p.get("suggested_price") or p.get("price") or p.get("suggested") or p.get("regular_price"))

    trust = _dec(p.get("trust_score") or p.get("provider_score") or p.get("supplier_score"))
    stock = None
    wp = p.get("warehouse_product") or {}
    if isinstance(wp, dict):
        stock = wp.get("stock")
    if stock is None:
        stock = p.get("stock")

    gallery = p.get("gallery") or p.get("images") or []
    images: List[str] = []
    if isinstance(gallery, list):
        for g in gallery:
            if isinstance(g, str):
                images.append(g)
            elif isinstance(g, dict):
                u = g.get("url") or g.get("src") or g.get("image")
                if u:
                    images.append(u)

    return {
        "source": "dropi",
        "source_product_id": str(pid) if pid is not None else None,
        "title": str(title)[:250],
        "description": str(desc)[:2000],
        "category_id": str(category_id) if category_id is not None else None,
        "category_name": str(category_name)[:120] if category_name else None,
        "cost": str(cost) if cost is not None else None,
        "suggested_price": str(suggested) if suggested is not None else None,
        "trust_score": str(trust) if trust is not None else None,
        "stock": int(stock) if stock is not None and str(stock).isdigit() else None,
        "images": images[:12],
        "raw": p,
    }

def _margin_pct(cost: Optional[Decimal], price: Optional[Decimal]) -> Optional[Decimal]:
    if cost is None or price is None or price <= 0:
        return None
    return (price - cost) / price

def _asset_score(n_images: int) -> float:
    # Simple saturating score: 0..1
    if n_images <= 0:
        return 0.0
    return min(1.0, n_images / 7.0)

def _default_score(prod: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    cost = _dec(prod.get("cost"))
    price = _dec(prod.get("suggested_price"))
    m = _margin_pct(cost, price)
    m_score = float(max(Decimal("0"), min(Decimal("1"), m or Decimal("0"))))
    a_score = _asset_score(len(prod.get("images") or []))
    trust = _dec(prod.get("trust_score"))
    t_score = float(max(Decimal("0"), min(Decimal("1"), (trust or Decimal("0")) / Decimal("10"))))
    score = 0.55 * m_score + 0.25 * a_score + 0.20 * t_score
    return score, {"m_score": m_score, "a_score": a_score, "t_score": t_score, "mode": "fallback"}

def _score_with_existing_engine(prod: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    # Best-effort: try to use existing BayesianScore if present.
    # If not, fallback to heuristic.
    try:
        # common patterns (may not exist in your repo)
        from core.bayesian_score import BayesianScore  # type: ignore
        bs = BayesianScore()  # type: ignore
        s = bs.score(prod)  # type: ignore
        # Expect either float or dict with 'score'
        if isinstance(s, dict) and "score" in s:
            return float(s["score"]), {"mode": "core.bayesian_score", **{k:v for k,v in s.items() if k!="raw"}}
        return float(s), {"mode": "core.bayesian_score"}
    except Exception:
        return _default_score(prod)

def _passes_primary_filters(prod: Dict[str, Any], args: FinderArgs) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    # Category filter
    if args.categories:
        cat = (prod.get("category_name") or "").lower()
        ok = any(c.lower() in cat for c in args.categories)
        if not ok:
            reasons.append("category_not_target")
    # Images
    if len(prod.get("images") or []) < args.min_images:
        reasons.append("insufficient_images")
    # Margin proxy (uses suggested_price; safe as proxy)
    cost = _dec(prod.get("cost"))
    price = _dec(prod.get("suggested_price"))
    mp = _margin_pct(cost, price)
    if mp is not None and mp < args.min_margin_pct:
        reasons.append("margin_proxy_below_threshold")
    if cost is None:
        reasons.append("missing_cost")
    # Optional: Stock must be positive if provided
    stock = prod.get("stock")
    if stock is not None and stock <= 0:
        reasons.append("out_of_stock")
    return (len(reasons) == 0), reasons

class DropiProductFinder:
    def __init__(self, ledger: Optional[LedgerWriter] = None) -> None:
        self.ledger = ledger or LedgerWriter()

    def snapshot_catalog(self, client: DropiClient, args: FinderArgs) -> Tuple[str, str, int]:
        daydir = os.path.join(args.output_dir, _date_dir())
        _mkdir(daydir)
        ts = _now_stamp()
        ndjson_path = os.path.join(daydir, f"catalog_{ts}.ndjson")
        manifest_path = os.path.join(daydir, f"manifest_{ts}.json")

        start = 0
        got = 0
        rows: List[Dict[str, Any]] = []

        while got < args.max_products:
            body = {
                "pageSize": int(args.page_size),
                "startData": int(start),
                "no_count": True,
                "order_by": "id",
                "order_type": "asc",
            }
            resp = client.post("/products/index", body)
            # Many Dropi responses include `objects` list.
            objects = resp.get("objects") if isinstance(resp, dict) else None
            if not objects:
                break
            for p in objects:
                rows.append(_normalize_product(p))
            got = len(rows)
            start += int(args.page_size)

        count = _ndjson_write(ndjson_path, rows)
        sha = _sha256_file(ndjson_path)

        manifest = {
            "source": "dropi",
            "created_utc": ts,
            "count": count,
            "sha256": sha,
            "page_size": args.page_size,
            "max_products": args.max_products,
            "filters": {
                "categories": args.categories or [],
                "min_images": args.min_images,
                "min_margin_pct_proxy": str(args.min_margin_pct),
            },
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        self.ledger.emit("CATALOG_SNAPSHOT_CREATED", {"ndjson_path": ndjson_path, "manifest_path": manifest_path, "sha256": sha, "count": count})
        return ndjson_path, manifest_path, count

    def shortlist(self, ndjson_path: str, args: FinderArgs) -> List[Dict[str, Any]]:
        # Stream read NDJSON
        candidates: List[Dict[str, Any]] = []
        with open(ndjson_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                prod = json.loads(line)
                ok, reasons = _passes_primary_filters(prod, args)
                if not ok:
                    continue
                score, breakdown = _score_with_existing_engine(prod)
                candidates.append({
                    "source_product_id": prod.get("source_product_id"),
                    "title": prod.get("title"),
                    "category_name": prod.get("category_name"),
                    "cost": prod.get("cost"),
                    "suggested_price": prod.get("suggested_price"),
                    "images_count": len(prod.get("images") or []),
                    "trust_score": prod.get("trust_score"),
                    "score": score,
                    "score_breakdown": breakdown,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        top = candidates[: args.top_n]
        return top

    def emit_top(self, top: List[Dict[str, Any]], args: FinderArgs, meta: Dict[str, Any]) -> str:
        _mkdir(os.path.dirname(args.evidence_path))
        payload = {"meta": meta, "top": top}
        with open(args.evidence_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        self.ledger.emit("LAUNCH_CANDIDATES_EMITTED", {"evidence_path": args.evidence_path, "top_n": len(top)})
        return args.evidence_path

def run(args: FinderArgs) -> Dict[str, Any]:
    cfg = _cfg_from_env()
    client = DropiClient(cfg)
    finder = DropiProductFinder()

    ndjson_path, manifest_path, count = finder.snapshot_catalog(client, args)
    top = finder.shortlist(ndjson_path, args)
    meta = {"ndjson_path": ndjson_path, "manifest_path": manifest_path, "catalog_count": count}
    evidence = finder.emit_top(top, args, meta)
    return {"catalog_count": count, "evidence": evidence, "top": top, "ndjson_path": ndjson_path, "manifest_path": manifest_path}
