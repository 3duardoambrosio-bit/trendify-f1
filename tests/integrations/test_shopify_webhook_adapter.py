from __future__ import annotations

import json

from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64
from synapse.integrations.shopify_webhook_adapter import handle_shopify_webhook_http


def test_adapter_accepts_ok_and_returns_json():
    secret = "shpss_test_secret"
    body = b'{"hello":"world","n":1}'
    h = compute_shopify_hmac_sha256_base64(secret, body)

    headers = {
        "x-shopify-hmac-sha256": h,  # lower-case to prove case-insensitive path works
        "X-Shopify-Webhook-Id": "wh_1",
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Shop-Domain": "example.myshopify.com",
    }

    resp = handle_shopify_webhook_http(secret=secret, headers=headers, body=body, dedup_set=set())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    data = json.loads(resp.body.decode("utf-8"))
    assert data["ok"] is True
    assert data["webhook_id"] == "wh_1"
    assert data["topic"] == "orders/create"
    assert data["shop_domain"] == "example.myshopify.com"


def test_adapter_rejects_invalid_hmac_401():
    secret = "shpss_test_secret"
    body = b'{"x":1}'
    headers = {"X-Shopify-Hmac-Sha256": "bogus=="}

    resp = handle_shopify_webhook_http(secret=secret, headers=headers, body=body, dedup_set=set())
    assert resp.status_code == 401
    data = json.loads(resp.body.decode("utf-8"))
    assert data["ok"] is False
    assert data["reason"] == "invalid_hmac"


def test_adapter_dedup_409():
    secret = "shpss_test_secret"
    body = b'{"x":1}'
    h = compute_shopify_hmac_sha256_base64(secret, body)

    headers = {"X-Shopify-Hmac-Sha256": h, "X-Shopify-Webhook-Id": "wh_dup"}
    d = set()

    r1 = handle_shopify_webhook_http(secret=secret, headers=headers, body=body, dedup_set=d)
    assert r1.status_code == 200

    r2 = handle_shopify_webhook_http(secret=secret, headers=headers, body=body, dedup_set=d)
    assert r2.status_code == 409
    data = json.loads(r2.body.decode("utf-8"))
    assert data["ok"] is False
    assert data["reason"] == "duplicate_webhook"