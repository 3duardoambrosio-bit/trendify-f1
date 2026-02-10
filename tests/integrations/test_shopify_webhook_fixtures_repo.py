from __future__ import annotations

import json
from pathlib import Path

from synapse.integrations.shopify_webhook_cli import main


def test_repo_fixture_orders_create_roundtrip(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    fx = repo / "fixtures" / "shopify_webhooks" / "orders_create"

    headers = fx / "headers.json"
    body = fx / "body.bin"
    assert headers.exists()
    assert body.exists()

    out_dir = tmp_path / "out"
    dedup = tmp_path / "dedup.json"

    rc1 = main([
        "--headers", str(headers),
        "--body", str(body),
        "--secret", "shpss_test_secret",
        "--dedup-file", str(dedup),
        "--out-dir", str(out_dir),
        "--quiet",
    ])
    assert rc1 == 0

    resp1 = json.loads((out_dir / "response.json").read_text(encoding="utf-8"))
    assert resp1["status_code"] == 200
    assert resp1["body_json"]["ok"] is True

    rc2 = main([
        "--headers", str(headers),
        "--body", str(body),
        "--secret", "shpss_test_secret",
        "--dedup-file", str(dedup),
        "--out-dir", str(out_dir),
        "--quiet",
    ])
    assert rc2 == 3

    resp2 = json.loads((out_dir / "response.json").read_text(encoding="utf-8"))
    assert resp2["status_code"] == 409
    assert resp2["body_json"]["reason"] == "duplicate_webhook"