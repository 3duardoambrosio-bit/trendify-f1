from __future__ import annotations

import zipfile
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


def test_bundle_zip_contains_expected_files(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.csv"
    _write_canonical(canonical, "p1")

    out_root = tmp_path / "out"
    rc = run(product_id="p1", dry_run=False, out_root=str(out_root), canonical_csv=str(canonical))
    assert rc == 0

    zpath = out_root / "p1" / "bundle.zip"
    assert zpath.exists()

    with zipfile.ZipFile(zpath, "r") as z:
        names = set(z.namelist())

    assert "creatives.ndjson" in names
    assert "quality.json" in names
    assert "meta/meta_assets.json" in names
    assert "shopify/shopify_products.csv" in names
