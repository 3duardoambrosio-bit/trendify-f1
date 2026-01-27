# scripts/dropi_enrich_dump_with_catalog.py
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable


ID_KEYS = [
    "product_id",
    "productId",
    "productID",
    "id",
    "codigo",
    "code",
    "sku",
    "external_id",
    "externalId",
]

NAME_HINTS = ("dropi", "catalog", "product", "producto", "export", "items", "inventario", "catalogo")
NEGATIVE_HINTS = ("dump", "candidates", "shortlist", "launch_candidates")

# what we consider "real catalog signals"
SIGNAL_RX = re.compile(r"(price|precio|image|imagen|img|photo|description|descripcion|desc|body|html)", re.I)


def _as_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _extract_id(obj: dict[str, Any]) -> str:
    for k in ID_KEYS:
        if k in obj:
            v = _as_str(obj.get(k))
            if v:
                return v
    return ""


def _walk_dicts(x: Any, depth: int = 0, max_depth: int = 12) -> Iterable[dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk_dicts(v, depth + 1, max_depth)
    elif isinstance(x, list):
        for v in x:
            yield from _walk_dicts(v, depth + 1, max_depth)


def _candidate_files_in_dir(d: Path) -> list[Path]:
    if not d.exists():
        return []
    out: list[Path] = []
    for ext in ("*.csv", "*.json"):
        out.extend(d.glob(ext))
    return [p for p in out if p.is_file()]


def _score_path(p: Path) -> int:
    name = p.name.lower()
    s = 0
    for h in NAME_HINTS:
        if h in name:
            s += 10
    for n in NEGATIVE_HINTS:
        if n in name:
            s -= 25
    if "catalog" in name or "catalogo" in name:
        s += 20
    if p.suffix.lower() == ".csv":
        s += 5
    return s


def _csv_has_signals(p: Path) -> bool:
    try:
        with p.open("r", encoding="utf-8", newline="") as f:
            first = f.readline()
        # crude header check
        return bool(SIGNAL_RX.search(first))
    except Exception:
        return False


def _json_has_signals(p: Path) -> bool:
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False

    # look at first ~200 dict nodes and see if any key matches signals
    seen = 0
    for d in _walk_dicts(obj, max_depth=10):
        for k in d.keys():
            if SIGNAL_RX.search(str(k)):
                return True
        seen += 1
        if seen >= 200:
            break
    return False


def _looks_like_real_catalog(p: Path) -> bool:
    if p.suffix.lower() == ".csv":
        return _csv_has_signals(p)
    if p.suffix.lower() == ".json":
        return _json_has_signals(p)
    return False


def _find_catalog_auto(dump_path: Path) -> Path | None:
    dump_path = dump_path.resolve()

    ev = Path("data") / "evidence"
    dl = Path.home() / "Downloads"
    cands = _candidate_files_in_dir(ev) + _candidate_files_in_dir(dl)
    if not cands:
        return None

    cands_sorted = sorted(cands, key=lambda p: (_score_path(p), p.stat().st_mtime), reverse=True)

    # pick first valid candidate that is NOT the dump and has signals
    for p in cands_sorted:
        try:
            rp = p.resolve()
        except Exception:
            continue
        if rp == dump_path:
            continue
        if not _looks_like_real_catalog(p):
            continue
        return p

    return None


def _load_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"catalog not found: {path}")

    if path.suffix.lower() == ".csv":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                rows.append({k: (v if v is not None else "") for k, v in row.items()})
        return rows

    obj = json.loads(path.read_text(encoding="utf-8"))
    dicts = list(_walk_dicts(obj))
    out: list[dict[str, Any]] = []
    for d in dicts:
        pid = _extract_id(d)
        if pid:
            out.append(d)
    return out


def _merge_source(existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(existing, dict):
        return dict(incoming)

    merged = dict(existing)
    for k, v in incoming.items():
        if k not in merged or merged.get(k) in (None, "", [], {}):
            merged[k] = v
    return merged


def _enrich_list(items: Any, catalog_index: dict[str, dict[str, Any]]) -> tuple[int, int]:
    if not isinstance(items, list):
        return (0, 0)

    enriched = 0
    missing = 0

    for it in items:
        if not isinstance(it, dict):
            continue
        pid = _as_str(it.get("product_id"))
        if not pid:
            continue
        src = catalog_index.get(pid)
        if not src:
            missing += 1
            continue
        it["source"] = _merge_source(it.get("source"), src)
        enriched += 1

    return enriched, missing


def _print_catalog_suggestions(dump_path: Path) -> None:
    ev = Path("data") / "evidence"
    dl = Path.home() / "Downloads"
    cands = _candidate_files_in_dir(ev) + _candidate_files_in_dir(dl)
    if not cands:
        print("No encontré ningún CSV/JSON en data/evidence ni Downloads.")
        return

    dump_path = dump_path.resolve()
    cands_sorted = sorted(cands, key=lambda p: (_score_path(p), p.stat().st_mtime), reverse=True)
    print("Catálogos candidatos (top 15) + señales:")
    for p in cands_sorted[:15]:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        same = " (ES EL DUMP)" if rp == dump_path else ""
        ok = "signals=YES" if _looks_like_real_catalog(p) else "signals=NO"
        print(f"- {p}  score={_score_path(p)}  {ok}{same}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, help="existing dump json (shortlist)")
    ap.add_argument("--catalog", default="auto", help="catalog export CSV/JSON (or 'auto')")
    ap.add_argument("--out", required=True, help="output enriched dump json")
    args = ap.parse_args(argv)

    dump_p = Path(args.dump)
    out_p = Path(args.out)

    if not dump_p.exists():
        print(f"ERROR: dump not found: {dump_p}")
        return 2

    dump = json.loads(dump_p.read_text(encoding="utf-8"))
    if not isinstance(dump, dict):
        print("ERROR: dump must be a JSON object at top-level")
        return 3

    cat_arg = (args.catalog or "").strip()
    if cat_arg.lower() == "auto":
        cat_p = _find_catalog_auto(dump_p)
        if not cat_p:
            print("ERROR: --catalog auto no encontró un catálogo real con señales (price/image/desc).")
            _print_catalog_suggestions(dump_p)
            return 4
    else:
        cat_p = Path(cat_arg)
        if not cat_p.exists():
            print(f"ERROR: catalog not found: {cat_p}")
            _print_catalog_suggestions(dump_p)
            return 4
        if cat_p.resolve() == dump_p.resolve():
            print("ERROR: catalog points to the same file as dump. That is not a catalog export.")
            _print_catalog_suggestions(dump_p)
            return 5

    catalog_rows = _load_catalog(cat_p)
    index: dict[str, dict[str, Any]] = {}
    for row in catalog_rows:
        pid = _extract_id(row)
        if pid and pid not in index:
            index[pid] = row

    e1, m1 = _enrich_list(dump.get("candidates"), index)
    e2, m2 = _enrich_list(dump.get("top"), index)

    meta = dump.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        dump["meta"] = meta
    meta["enriched_from_catalog"] = str(cat_p)
    meta["enrich_stats"] = {
        "catalog_rows_seen": len(catalog_rows),
        "catalog_index_size": len(index),
        "candidates": {"enriched": e1, "missing": m1},
        "top": {"enriched": e2, "missing": m2},
    }

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("dropi_enrich_dump_with_catalog: OK")
    print(f"- dump_in:  {dump_p}")
    print(f"- catalog:  {cat_p}")
    print(f"- dump_out: {out_p}")
    print(f"- stats: {meta['enrich_stats']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
