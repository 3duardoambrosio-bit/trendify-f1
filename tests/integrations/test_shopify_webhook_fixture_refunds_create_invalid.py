from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64


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


def test_fixture_refunds_create_invalid_payload_fails_closed(tmp_path: Path) -> None:
    secret = "shpss_test_secret"
    fx = tmp_path / "refunds_create_invalid"
    fx.mkdir(parents=True, exist_ok=True)

    body = {
        "id": 9001,
        "created_at": "2026-03-08T10:00:00Z",
        "transactions": [{"kind": "refund", "status": "success", "amount": "10.00", "currency": "MXN"}],
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    (fx / "body.bin").write_bytes(body_bytes)

    headers = {
        "X-Shopify-Hmac-Sha256": compute_shopify_hmac_sha256_base64(secret, body_bytes),
        "X-Shopify-Webhook-Id": "wh_refunds_invalid_1",
        "X-Shopify-Topic": "refunds/create",
        "X-Shopify-Shop-Domain": "example.myshopify.com",
    }
    (fx / "headers.json").write_text(json.dumps(headers, ensure_ascii=False, indent=2), encoding="utf-8")

    r = _run_cli(fx, secret)
    assert r.returncode == 1

    out_dir = fx / "out"
    assert (out_dir / "status_code.txt").read_text(encoding="utf-8").strip() == "422"

    meta = json.loads((out_dir / "processing_metadata.json").read_text(encoding="utf-8"))
    assert meta["webhook_topic"] == "refunds/create"
    assert meta["refund_processed"] is False
    assert meta["refund_recorded"] is False

    dedup = out_dir / "dedup.json"
    if dedup.exists():
        raw = json.loads(dedup.read_text(encoding="utf-8"))
        assert raw == []