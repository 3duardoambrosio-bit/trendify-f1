from __future__ import annotations

from pathlib import Path

from synapse.marketing_os.wave_kit_runner import _resolve_canonical_csv, run
from synapse.marketing_os.wave_kit_manifest import read_manifest


def test_resolve_canonical_by_scan(tmp_path: Path, monkeypatch) -> None:
    # simulate cwd with data/ folder
    (tmp_path / "data" / "catalog").mkdir(parents=True, exist_ok=True)
    good = tmp_path / "data" / "catalog" / "canonical_products.csv"
    good.write_text("product_id,title,description\np1,T,Desc\n", encoding="utf-8", newline="\n")

    # change cwd for resolver behavior
    monkeypatch.chdir(tmp_path)

    p = _resolve_canonical_csv(None)
    assert p is not None
    assert "canonical" in p.name.lower()


def test_apply_fallback_minimal_creates_outputs(tmp_path: Path, monkeypatch) -> None:
    # no data/ folder at all => fallback
    monkeypatch.chdir(tmp_path)

    out_root = tmp_path / "out"
    rc = run(product_id="p1", dry_run=False, out_root=str(out_root), canonical_csv=None)
    assert rc == 0

    root = out_root / "p1"
    assert (root / "meta" / "meta_assets.json").exists()
    assert (root / "shopify" / "shopify_products.csv").exists()
    assert (root / "manifest.json").exists()

    m = read_manifest(root / "manifest.json")
    assert m["meta"]["catalog_mode"] == "fallback_minimal"
