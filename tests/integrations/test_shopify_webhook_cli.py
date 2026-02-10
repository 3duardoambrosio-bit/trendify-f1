from __future__ import annotations

import json
from pathlib import Path

from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64
from synapse.integrations.shopify_webhook_cli import main


def _write_json(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_cli_accepts_and_writes_artifacts(tmp_path: Path):
    secret = "shpss_test_secret"
    body = b'{"hello":"world","n":1}'
    h = compute_shopify_hmac_sha256_base64(secret, body)

    headers = {
        "x-shopify-hmac-sha256": h,
        "X-Shopify-Webhook-Id": "wh_cli_1",
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Shop-Domain": "example.myshopify.com",
    }

    headers_path = tmp_path / "headers.json"
    body_path = tmp_path / "body.bin"
    secret_path = tmp_path / "secret.txt"
    out_dir = tmp_path / "out"
    dedup_path = tmp_path / "dedup.json"

    _write_json(headers_path, headers)
    body_path.write_bytes(body)
    secret_path.write_text(secret, encoding="utf-8")

    rc = main([
        "--headers", str(headers_path),
        "--body", str(body_path),
        "--secret-file", str(secret_path),
        "--dedup-file", str(dedup_path),
        "--out-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == 0

    resp = json.loads((out_dir / "response.json").read_text(encoding="utf-8"))
    assert resp["status_code"] == 200
    assert resp["body_json"]["ok"] is True
    assert resp["body_json"]["webhook_id"] == "wh_cli_1"

    # result is JSON-safe (raw_body converted)
    assert resp["result"]["event"]["raw_body_b64"] != ""

    sc = (out_dir / "status_code.txt").read_text(encoding="utf-8").strip()
    assert sc == "200"

    d = json.loads(dedup_path.read_text(encoding="utf-8"))
    assert "wh_cli_1" in d


def test_cli_rejects_invalid_hmac(tmp_path: Path):
    secret = "shpss_test_secret"
    body = b'{"x":1}'
    headers = {"X-Shopify-Hmac-Sha256": "bogus=="}

    headers_path = tmp_path / "headers.json"
    body_path = tmp_path / "body.bin"
    out_dir = tmp_path / "out"

    _write_json(headers_path, headers)
    body_path.write_bytes(body)

    rc = main([
        "--headers", str(headers_path),
        "--body", str(body_path),
        "--secret", secret,
        "--out-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == 3

    resp = json.loads((out_dir / "response.json").read_text(encoding="utf-8"))
    assert resp["status_code"] == 401
    assert resp["body_json"]["ok"] is False
    assert resp["body_json"]["reason"] == "invalid_hmac"


def test_cli_dedup_persisted_across_runs(tmp_path: Path):
    secret = "shpss_test_secret"
    body = b'{"x":1}'
    h = compute_shopify_hmac_sha256_base64(secret, body)
    headers = {"X-Shopify-Hmac-Sha256": h, "X-Shopify-Webhook-Id": "wh_cli_dup"}

    headers_path = tmp_path / "headers.json"
    body_path = tmp_path / "body.bin"
    out_dir = tmp_path / "out"
    dedup_path = tmp_path / "dedup.json"

    _write_json(headers_path, headers)
    body_path.write_bytes(body)

    rc1 = main([
        "--headers", str(headers_path),
        "--body", str(body_path),
        "--secret", secret,
        "--dedup-file", str(dedup_path),
        "--out-dir", str(out_dir),
        "--quiet",
    ])
    assert rc1 == 0

    rc2 = main([
        "--headers", str(headers_path),
        "--body", str(body_path),
        "--secret", secret,
        "--dedup-file", str(dedup_path),
        "--out-dir", str(out_dir),
        "--quiet",
    ])
    assert rc2 == 3

    resp2 = json.loads((out_dir / "response.json").read_text(encoding="utf-8"))
    assert resp2["status_code"] == 409
    assert resp2["body_json"]["reason"] == "duplicate_webhook"