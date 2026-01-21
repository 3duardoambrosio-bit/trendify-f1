from __future__ import annotations

import json
from pathlib import Path

from synapse.marketing_os.wave_kit_runner import run


def _write_canonical(csv_path: Path, product_id: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "product_id,title,description\n"
        f"{product_id},Producto X,Desc X\n",
        encoding="utf-8",
        newline="\n",
    )


def test_wavekit_dry_run_creates_nothing(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.csv"
    _write_canonical(canonical, "p1")

    rc = run(product_id="p1", dry_run=True, out_root=str(tmp_path / "out"), canonical_csv=str(canonical))
    assert rc == 0
    assert not (tmp_path / "out" / "p1").exists()


def test_wavekit_apply_writes_artifacts_bundle_quality_and_manifest(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.csv"
    _write_canonical(canonical, "p1")

    out_root = tmp_path / "out"
    rc = run(product_id="p1", dry_run=False, out_root=str(out_root), canonical_csv=str(canonical))
    assert rc == 0

    root = out_root / "p1"
    assert (root / "meta" / "meta_assets.json").exists()
    assert (root / "shopify" / "shopify_products.csv").exists()
    assert (root / "creatives.ndjson").exists()
    assert (root / "quality.json").exists()
    assert (root / "bundle.zip").exists()
    assert (root / "manifest.json").exists()

    raw = (root / "manifest.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")

    q = json.loads((root / "quality.json").read_text(encoding="utf-8"))
    assert 0 <= int(q["score"]) <= 100
    assert "metrics" in q
    assert "dedup_dropped" in q
