from __future__ import annotations

import json
from pathlib import Path

import subprocess


def test_dropi_autopick_creates_shortlist(tmp_path: Path) -> None:
    dump = tmp_path / "dump.json"
    out = tmp_path / "shortlist.csv"

    data = {
        "items": [
            {"id": "p1", "title": "Producto A", "rating": 4.8, "reviews_count": 500, "price": 29.99, "images": ["x.jpg"]},
            {"id": "p2", "title": "Producto B", "rating": 4.2, "reviews_count": 10, "price": 9.99, "images": []},
        ]
    }
    dump.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    r = subprocess.run(
        ["python", "scripts/dropi_autopick.py", "--dump", str(dump), "--out", str(out), "--n", "1"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert out.exists()
    txt = out.read_text(encoding="utf-8")
    assert "product_id" in txt
    assert "p1" in txt  # should pick best scored