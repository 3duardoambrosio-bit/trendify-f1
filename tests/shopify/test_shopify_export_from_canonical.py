from __future__ import annotations

import subprocess
from pathlib import Path


def test_shopify_export_from_canonical_generates_fuller_schema(tmp_path: Path) -> None:
    kit = tmp_path / "seed"
    (kit / "shopify").mkdir(parents=True, exist_ok=True)

    canonical = tmp_path / "canonical_products.csv"
    canonical.write_text(
        "product_id,title,description,price,compare_at_price,image_url,tags\n"
        "seed,Seed Product,Descripcion,29.99,49.99,https://example.com/a.jpg,\"a,b\"\n",
        encoding="utf-8",
        newline="\n",
    )

    r = subprocess.run(
        ["python", "scripts/shopify_export_from_canonical.py", "--kit-dir", str(kit), "--canonical-csv", str(canonical)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    out = kit / "shopify" / "shopify_products.csv"
    assert out.exists()
    txt = out.read_text(encoding="utf-8")
    assert "Variant Price" in txt
    assert "Image Src" in txt
    assert "https://example.com/a.jpg" in txt
    assert "Seed Product" in txt