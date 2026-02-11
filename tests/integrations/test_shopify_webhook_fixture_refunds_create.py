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
    assert (fx / "out" / "status_code.txt").read_text(encoding="utf-8").strip() == "200"

    r2 = _run_cli(fx, secret)
    assert r2.returncode == 3
    assert (fx / "out" / "status_code.txt").read_text(encoding="utf-8").strip() == "409"

    meta = json.loads((fx / "out" / "processing_metadata.json").read_text(encoding="utf-8"))
    assert meta["webhook_topic"] == "refunds/create"
    assert meta["shop_domain"] == "example.myshopify.com"
    assert meta["dedup_result"] == "duplicate"