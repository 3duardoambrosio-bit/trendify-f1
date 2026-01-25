from __future__ import annotations

import json
from pathlib import Path
import subprocess


def test_build_canonical_v2_extracts_price_image_tags(tmp_path: Path) -> None:
    dump = tmp_path / "dump.json"
    shortlist = tmp_path / "shortlist.csv"
    out = tmp_path / "canonical.csv"

    data = {
        "items": [
            {
                "id": "seed",
                "title": "Seed Product",
                "description": "Descripcion larga",
                "price": "$29.99",
                "compare_at_price": "$49.99",
                "images": [{"url": "https://example.com/a.jpg"}],
                "tags": ["gadget", "top"],
                "stock": 12,
                "sku": "SKU-SEED",
                "grams": 250
            }
        ]
    }
    dump.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    shortlist.write_text("product_id\nseed\n", encoding="utf-8", newline="\n")

    r = subprocess.run(
        ["python", "scripts/build_canonical_from_dropi_v2.py", "--shortlist", str(shortlist), "--dump", str(dump), "--out", str(out)],
        capture_output=True,
        text=True
    )
    assert r.returncode == 0, r.stderr
    txt = out.read_text(encoding="utf-8")
    assert "compare_at_price" in txt
    assert "29.99" in txt
    assert "https://example.com/a.jpg" in txt
    assert "gadget" in txt