from __future__ import annotations

import json
from pathlib import Path
import subprocess


def test_enrich_shopify_csv_fills_body(tmp_path: Path) -> None:
    kit = tmp_path / "seed"
    (kit / "shopify").mkdir(parents=True, exist_ok=True)

    # empty body
    csv_path = kit / "shopify" / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Body (HTML),Vendor,Tags,Status\n"
        "seed-product,Seed Product,,TrendifyHub,\"synapse, wavekit\",draft\n",
        encoding="utf-8",
        newline="\n",
    )

    # creatives with a description
    nd = kit / "creatives.ndjson"
    nd.write_text(json.dumps({"description": "Línea 1\nLínea 2"}), encoding="utf-8")

    r = subprocess.run(
        ["python", "scripts/enrich_shopify_csv.py", "--kit-dir", str(kit)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    out = csv_path.read_text(encoding="utf-8")
    assert "<ul>" in out or "<p>" in out
    assert "Línea" in out