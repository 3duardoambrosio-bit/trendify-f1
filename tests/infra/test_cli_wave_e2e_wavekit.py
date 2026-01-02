from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cli_wave_apply_wavekit_writes_outputs(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.csv"
    canonical.write_text(
        "product_id,title,description\np1,Producto X,Desc X\n",
        encoding="utf-8",
        newline="\n",
    )
    out_root = tmp_path / "out"

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "wave",
            "--apply",
            "--product-id",
            "p1",
            "--canonical-csv",
            str(canonical),
            "--out-root",
            str(out_root),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "wave: OK" in (r.stdout or "")

    root = out_root / "p1"
    assert (root / "meta" / "meta_assets.json").exists()
    assert (root / "shopify" / "shopify_products.csv").exists()
    assert (root / "manifest.json").exists()
