# tests/webhooks/test_webhook_router.py
import json
import pytest

from synapse.webhooks import WebhookRouter, compute_hmac_sha256, WebhookError


def test_hmac_roundtrip():
    secret = "abc"
    body = b'{"x":1}'
    sig = compute_hmac_sha256(secret, body)
    assert isinstance(sig, str)
    assert len(sig) == 64


def test_router_rejects_invalid_signature():
    r = WebhookRouter()

    def handler(ev):
        return {"ok": True}

    r.register("meta", "purchase", handler)

    body = b'{"x":1}'
    with pytest.raises(WebhookError):
        r.handle(provider="meta", event_type="purchase", raw_body=body, secret="abc", signature_hex="deadbeef")


def test_router_routes_event_when_signature_ok():
    r = WebhookRouter()
    got = {"n": 0}

    def handler(ev):
        got["n"] += 1
        assert ev.provider == "meta"
        assert ev.event_type == "purchase"
        assert ev.payload["order_id"] == "1"
        return {"status": "accepted"}

    r.register("meta", "purchase", handler)

    body = json.dumps({"order_id": "1"}).encode("utf-8")
    sig = compute_hmac_sha256("secret", body)
    out = r.handle(provider="meta", event_type="purchase", raw_body=body, secret="secret", signature_hex=sig)
    assert out["status"] == "accepted"
    assert got["n"] == 1
