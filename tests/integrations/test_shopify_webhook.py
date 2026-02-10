from __future__ import annotations

from synapse.integrations.shopify_webhook import (
    compute_shopify_hmac_sha256_base64,
    process_shopify_webhook,
    verify_shopify_hmac_sha256,
)


def test_shopify_hmac_ok_case_insensitive_headers():
    secret = "shpss_test_secret"
    body = b'{"hello":"world","n":1}'
    h = compute_shopify_hmac_sha256_base64(secret, body)

    headers = {
        "x-shopify-hmac-sha256": h,
        "X-Shopify-Webhook-Id": "wh_1",
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Shop-Domain": "example.myshopify.com",
    }

    assert verify_shopify_hmac_sha256(secret, body, headers["x-shopify-hmac-sha256"]) is True
    r = process_shopify_webhook(secret=secret, headers=headers, body=body, dedup_set=set())
    assert r.accepted is True
    assert r.status_code == 200
    assert r.reason == "ok"
    assert r.event is not None
    assert r.event.webhook_id == "wh_1"
    assert r.event.payload["hello"] == "world"


def test_shopify_hmac_invalid_rejected():
    secret = "shpss_test_secret"
    body = b'{"x":1}'
    headers = {"X-Shopify-Hmac-Sha256": "bogus=="}
    r = process_shopify_webhook(secret=secret, headers=headers, body=body, dedup_set=set())
    assert r.accepted is False
    assert r.status_code == 401
    assert r.reason == "invalid_hmac"
    assert r.event is None


def test_shopify_webhook_dedup_409():
    secret = "shpss_test_secret"
    body = b'{"x":1}'
    good = compute_shopify_hmac_sha256_base64(secret, body)
    headers = {"X-Shopify-Hmac-Sha256": good, "X-Shopify-Webhook-Id": "wh_dup"}
    d = set()

    r1 = process_shopify_webhook(secret=secret, headers=headers, body=body, dedup_set=d)
    assert r1.accepted is True
    assert r1.status_code == 200

    r2 = process_shopify_webhook(secret=secret, headers=headers, body=body, dedup_set=d)
    assert r2.accepted is False
    assert r2.status_code == 409
    assert r2.reason == "duplicate_webhook"