from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _run_cli(fixture_dir: Path, secret: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "synapse.integrations.shopify_webhook_cli",
        "--fixture-dir",
        str(fixture_dir),
        "--secret",
        secret,
        "--quiet",
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_fixture_refunds_create_roundtrip(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    src = repo / "fixtures" / "shopify_webhooks" / "refunds_create"
    assert (src / "body.bin").exists()
    assert (src / "headers.json").exists()

    fx = tmp_path / "refunds_create"
    fx.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / "body.bin", fx / "body.bin")
    shutil.copyfile(src / "headers.json", fx / "headers.json")

    secret = "shpss_test_secret"

    r1 = _run_cli(fx, secret)
    assert r1.returncode == 0
    out_dir = fx / "out"
    assert (out_dir / "status_code.txt").read_text(encoding="utf-8").strip() == "200"
    assert (out_dir / "refund_event.json").exists()
    assert (out_dir / "refund_registry.ndjson").exists()

    meta1 = json.loads((out_dir / "processing_metadata.json").read_text(encoding="utf-8"))
    assert meta1["webhook_topic"] == "refunds/create"
    assert meta1["shop_domain"] == "example.myshopify.com"
    assert meta1["dedup_result"] == "new"
    assert meta1["refund_processed"] is True
    assert meta1["refund_recorded"] is True

    lines1 = (out_dir / "refund_registry.ndjson").read_text(encoding="utf-8").splitlines()
    assert len(lines1) == 1

    r2 = _run_cli(fx, secret)
    assert r2.returncode == 3
    assert (out_dir / "status_code.txt").read_text(encoding="utf-8").strip() == "409"

    meta2 = json.loads((out_dir / "processing_metadata.json").read_text(encoding="utf-8"))
    assert meta2["webhook_topic"] == "refunds/create"
    assert meta2["shop_domain"] == "example.myshopify.com"
    assert meta2["dedup_result"] == "duplicate"

    lines2 = (out_dir / "refund_registry.ndjson").read_text(encoding="utf-8").splitlines()
    assert len(lines2) == 1