from __future__ import annotations

import json
from pathlib import Path
import subprocess


def test_canonical_quality_gate_seed_exception(tmp_path: Path) -> None:
    report = tmp_path / "canonical_products.report.json"
    report.write_text(json.dumps({
        "stats": {"total_ids": 1, "with_price": 0, "with_image": 0, "with_desc": 0},
        "fill_rates": {"with_price": 0.0, "with_image": 0.0, "with_desc": 0.0}
    }), encoding="utf-8")

    r = subprocess.run(
        ["python", "scripts/canonical_quality_gate.py", "--report", str(report), "--allow-seed"],
        capture_output=True,
        text=True
    )
    assert r.returncode == 0, r.stderr


def test_canonical_quality_gate_fails_when_missing_fields(tmp_path: Path) -> None:
    report = tmp_path / "canonical_products.report.json"
    report.write_text(json.dumps({
        "stats": {"total_ids": 2, "with_price": 0, "with_image": 0, "with_desc": 0},
        "fill_rates": {"with_price": 0.0, "with_image": 0.0, "with_desc": 0.0}
    }), encoding="utf-8")

    r = subprocess.run(
        ["python", "scripts/canonical_quality_gate.py", "--report", str(report)],
        capture_output=True,
        text=True
    )
    assert r.returncode != 0