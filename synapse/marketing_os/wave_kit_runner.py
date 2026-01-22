from __future__ import annotations

import csv
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse.infra.contract_snapshot import stable_json_dumps
from synapse.infra.dry_run import DryRunDecision, format_dry_run_banner
from synapse.infra.logging_std import get_logger, log_kv
from synapse.marketing_os.creative_dedup import dedup_creatives
from synapse.marketing_os.exporters.meta_bundle import write_meta_bundle
from synapse.marketing_os.exporters.shopify_pack import write_shopify_products_csv
from synapse.marketing_os.experiment_stoploss import default_policy_mx
from synapse.marketing_os.quality_scoring import score_creatives
from synapse.marketing_os.wave_kit_manifest import Artifact, artifact_from_file, build_manifest, write_manifest


@dataclass(frozen=True)
class WaveKitPaths:
    root: Path
    meta_dir: Path
    shopify_dir: Path
    manifest_path: Path
    creatives_ndjson: Path
    quality_json: Path
    bundle_zip: Path


def _read_csv_header(path: Path) -> list[str]:
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                line = f.readline()
            if not line:
                return []
            return [h.strip() for h in line.strip().split(",") if h.strip()]
        except Exception:
            continue
    return []


def _score_canonical_candidate(path: Path) -> int:
    name = path.name.lower()
    score = 0
    if "canonical" in name:
        score += 5

    hdr = [h.lower() for h in _read_csv_header(path)]
    if not hdr:
        return -1

    if "product_id" in hdr or "id" in hdr:
        score += 3
    if "title" in hdr or "name" in hdr or "product_name" in hdr:
        score += 2
    if "description" in hdr or "desc" in hdr:
        score += 1

    return score


def _resolve_canonical_csv(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"canonical_csv not found: {p}")
        return p

    candidates = [
        Path("data/catalog/canonical.csv"),
        Path("data/catalog/canonical_products.csv"),
        Path("data/catalog/canonical_products_v1.csv"),
        Path("data/catalog/products.csv"),
        Path("data/pipeline/canonical.csv"),
        Path("data/pipeline/canonical_products.csv"),
        Path("data/canonical.csv"),
    ]
    for c in candidates:
        if c.exists():
            return c

    base = Path("data")
    if not base.exists():
        return None

    found: list[Path] = []
    for pat in ("*canonical*.csv", "*.csv"):
        for p in base.rglob(pat):
            if p.is_file():
                found.append(p)
                if len(found) >= 250:
                    break
        if found and pat == "*canonical*.csv":
            break

    if not found:
        return None

    scored = [(p, _score_canonical_candidate(p)) for p in found]
    scored = [(p, s) for (p, s) in scored if s >= 0]
    if not scored:
        return None

    scored.sort(key=lambda ps: (-ps[1], len(str(ps[0]))))
    return scored[0][0]


def _load_product(canonical_csv: Path, product_id: str) -> dict[str, Any]:
    with canonical_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            pid = str(row.get("product_id") or row.get("id") or "").strip()
            if pid == product_id:
                return dict(row)
    raise KeyError(f"product_id not found in canonical_csv: {product_id}")


def _minimal_product(product_id: str) -> dict[str, Any]:
    return {"product_id": product_id, "title": product_id, "description": "", "handle": product_id}


def _pick_title(product: dict[str, Any], fallback: str) -> str:
    return str(product.get("title") or product.get("name") or product.get("product_name") or fallback).strip() or fallback


def _pick_desc(product: dict[str, Any]) -> str:
    return str(product.get("description") or product.get("desc") or "").strip()


def _pick_benefit(product: dict[str, Any]) -> str:
    return str(product.get("benefit") or product.get("hook") or product.get("usp") or "mejor valor").strip()


def _generate_creatives_raw(product: dict[str, Any]) -> list[dict[str, Any]]:
    title = _pick_title(product, "Producto")
    benefit = _pick_benefit(product)

    # Copy angles: directo, social proof, urgencia, outcome
    templates = [
        ("Directo", "{title} que sí cumple: {benefit}."),
        ("Upgrade", "Upgrade inmediato: {title}. {benefit}."),
        ("Outcome", "Resultados que se notan: {title}."),
        ("Social", "La gente que sabe, elige {title}."),
        ("Fricción", "Menos batallar, más avanzar: {title}."),
        ("Valor", "Lo barato sale caro. Mejor: {title}."),
        ("Descubrimiento", "Lo necesitas, aunque no lo sabías: {title}."),
        ("Disciplina", "Menos excusas, más acción: {title}."),
        ("Tiempo", "Tu día a día, pero en modo PRO: {title}."),
        ("CTA", "Pruébalo hoy: {title}."),
        ("Hook", "{title} + {benefit} = combo ganador."),
        ("Simple", "Hazlo fácil: {title} y listo."),
    ]

    out: list[dict[str, Any]] = []
    for i, (angle, t) in enumerate(templates, start=1):
        txt = t.format(title=title, benefit=benefit).strip()
        out.append(
            {
                "creative_id": f"c{i}",
                "angle": angle,
                "primary_text": txt,
                "headline": f"{title} | {benefit}".strip(),
                "description": f"Oferta limitada para {title}".strip(),
                "cta": "Shop Now",
            }
        )
    return out


def _write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(stable_json_dumps(r) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json_dumps(payload) + "\n", encoding="utf-8", newline="\n")


def _write_bundle_zip(bundle_path: Path, *, base_dir: Path, relpaths: list[str]) -> None:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rp in relpaths:
            p = base_dir / rp
            if p.exists() and p.is_file():
                z.write(p, arcname=rp)


def plan_paths(*, out_root: Path, product_id: str) -> WaveKitPaths:
    root = out_root / product_id
    return WaveKitPaths(
        root=root,
        meta_dir=root / "meta",
        shopify_dir=root / "shopify",
        manifest_path=root / "manifest.json",
        creatives_ndjson=root / "creatives.ndjson",
        quality_json=root / "quality.json",
        bundle_zip=root / "bundle.zip",
    )


def run(
    *,
    product_id: str,
    dry_run: bool = True,
    out_root: str | None = None,
    canonical_csv: str | None = None,
    schema_version: str = "wavekit-v2",
) -> int:
    lg = get_logger("synapse.wave_kit_runner")
    out_root_p = Path(out_root) if out_root else Path("data/marketing/waves")
    paths = plan_paths(out_root=out_root_p, product_id=product_id)

    decision = DryRunDecision(dry_run=dry_run, reason="cli_or_default")
    banner = format_dry_run_banner(decision, "wavekit")
    log_kv(lg, banner, product_id=product_id, out=str(paths.root))

    if dry_run:
        return 0

    csv_path = _resolve_canonical_csv(canonical_csv)
    used_fallback = False
    if csv_path is None:
        used_fallback = True
        product = _minimal_product(product_id)
    else:
        try:
            product = _load_product(csv_path, product_id)
        except KeyError:
            used_fallback = True
            product = _minimal_product(product_id)

    raw_creatives = _generate_creatives_raw(product)
    dres = dedup_creatives(raw_creatives, threshold=0.80)
    creatives = dres.kept

    _write_ndjson(paths.creatives_ndjson, creatives)

    title = _pick_title(product, product_id)
    q = score_creatives(creatives, title=title)
    q_payload = {"score": q.score, "metrics": q.metrics, "dedup_dropped": dres.dropped}
    _write_json(paths.quality_json, q_payload)

    meta_json = write_meta_bundle(paths.meta_dir, product_id=product_id, creatives=creatives)
    shopify_csv = write_shopify_products_csv(
        paths.shopify_dir,
        product={
            "title": title,
            "description": _pick_desc(product),
            "handle": product.get("handle") or title or product_id,
        },
        tags=["synapse", "wavekit"],
        vendor="TrendifyHub",
        status="draft",
    )

    # bundle (core deliverables)
    rels = [
        "creatives.ndjson",
        "quality.json",
        "meta/meta_assets.json",
        "shopify/shopify_products.csv",
    ]
    _write_bundle_zip(paths.bundle_zip, base_dir=paths.root, relpaths=rels)

    base_dir = paths.root
    artifacts: list[Artifact] = [
        artifact_from_file(paths.creatives_ndjson, base_dir=base_dir),
        artifact_from_file(paths.quality_json, base_dir=base_dir),
        artifact_from_file(meta_json, base_dir=base_dir),
        artifact_from_file(shopify_csv, base_dir=base_dir),
        artifact_from_file(paths.bundle_zip, base_dir=base_dir),
    ]

    policy = default_policy_mx()
    manifest = build_manifest(
        product_id=product_id,
        schema_version=schema_version,
        artifacts=artifacts,
        meta={
            "canonical_csv": str(csv_path) if csv_path is not None else None,
            "catalog_mode": "fallback_minimal" if used_fallback else "canonical",
            "creative_count": len(creatives),
            "quality_score": q.score,
            "dedup_dropped": dres.dropped,
            "stoploss_policy": {
                "roas_min": policy.roas_min,
                "max_spend_mxn": policy.max_spend_mxn,
                "min_events": policy.min_events,
            },
        },
    )
    write_manifest(paths.manifest_path, manifest)
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="synapse.marketing_os.wave_kit_runner")
    p.add_argument("--product-id", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--out-root", default=None)
    p.add_argument("--canonical-csv", default=None)
    args = p.parse_args(argv)

    return run(
        product_id=str(args.product_id),
        dry_run=not bool(args.apply),
        out_root=args.out_root,
        canonical_csv=args.canonical_csv,
    )
