from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_wave_apply_works_without_data_catalog(tmp_path: Path) -> None:
    # Run from a clean cwd with no data/ folder. Provide PYTHONPATH to repo root so imports work.
    repo_root = Path(__file__).resolve().parents[2]
    out_root = tmp_path / "out"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root)

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "synapse.cli",
            "wave",
            "--apply",
            "--product-id",
            "p1",
            "--out-root",
            str(out_root),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)

    root = out_root / "p1"
    assert (root / "meta" / "meta_assets.json").exists()
    assert (root / "shopify" / "shopify_products.csv").exists()
    assert (root / "manifest.json").exists()
