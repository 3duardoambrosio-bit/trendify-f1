from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64


def _write_fixture(dir_path: Path, *, secret: str, shop: str, webhook_id: str, topic: str, body_text: str, hmac_override: str | None = None) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)

    body_bytes = body_text.encode("utf-8")
    (dir_path / "body.bin").write_bytes(body_bytes)

    hmac_val = hmac_override if hmac_override is not None else compute_shopify_hmac_sha256_base64(secret, body_bytes)

    headers = {
        "X-Shopify-Hmac-Sha256": hmac_val,
        "X-Shopify-Webhook-Id": webhook_id,
        "X-Shopify-Topic": topic,
        "X-Shopify-Shop-Domain": shop,
    }
    (dir_path / "headers.json").write_text(json.dumps(headers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def test_cli_accepts_200_and_writes_status(tmp_path: Path) -> None:
    secret = "shpss_test_secret"
    fx = tmp_path / "orders_create"
    _write_fixture(
        fx,
        secret=secret,
        shop="example.myshopify.com",
        webhook_id="wh_test_1",
        topic="orders/create",
        body_text='{"hello":"world","n":1}',
    )

    r = _run_cli(fx, secret)
    assert r.returncode == 0
    assert (fx / "out" / "status_code.txt").read_text(encoding="utf-8").strip() == "200"


def test_cli_rejects_invalid_hmac_401(tmp_path: Path) -> None:
    secret = "shpss_test_secret"
    fx = tmp_path / "orders_create_bad_hmac"
    _write_fixture(
        fx,
        secret=secret,
        shop="example.myshopify.com",
        webhook_id="wh_test_2",
        topic="orders/create",
        body_text='{"x":1}',
        hmac_override="NOT_A_REAL_HMAC_44_CHARS____________________",
    )

    r = _run_cli(fx, secret)
    assert r.returncode == 2
    assert (fx / "out" / "status_code.txt").read_text(encoding="utf-8").strip() == "401"


def test_cli_dedup_persisted_across_runs_409(tmp_path: Path) -> None:
    secret = "shpss_test_secret"
    fx = tmp_path / "orders_paid"
    _write_fixture(
        fx,
        secret=secret,
        shop="example.myshopify.com",
        webhook_id="wh_test_3",
        topic="orders/paid",
        body_text='{"order_id":123,"status":"paid"}',
    )

    r1 = _run_cli(fx, secret)
    assert r1.returncode == 0
    assert (fx / "out" / "status_code.txt").read_text(encoding="utf-8").strip() == "200"

    r2 = _run_cli(fx, secret)
    assert r2.returncode == 3
    assert (fx / "out" / "status_code.txt").read_text(encoding="utf-8").strip() == "409"

    dedup = json.loads((fx / "out" / "dedup.json").read_text(encoding="utf-8"))
    assert "example.myshopify.com:wh_test_3" in dedup