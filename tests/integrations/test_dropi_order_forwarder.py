# tests/integrations/test_dropi_order_forwarder.py
import json
import pytest

from synapse.integrations.dropi.order_forwarder import (
    DropiOrderForwarder,
    DropiOrderForwarderConfig,
    InMemoryIdempotencyStore,
    CircuitOpenError,
)

ORDER = {
    "id": 123,
    "currency": "MXN",
    "email": "lalo@example.com",
    "customer": {"email": "lalo@example.com", "first_name": "Lalo", "last_name": "ACERO"},
    "shipping_address": {"name": "Lalo", "address1": "Calle 1", "city": "CDMX", "zip": "00000", "country": "MX"},
    "line_items": [{"sku": "SKU1", "title": "Prod 1", "quantity": 2, "price": "99.50"}],
    "total_price": "199.00",
}

class DummyTransport:
    def __init__(self, *, status=201, body=b'{"ok":true}', raise_exc=False):
        self.calls = []
        self.status = status
        self.body = body
        self.raise_exc = raise_exc

    def request(self, method, url, headers, body, timeout_seconds):
        self.calls.append((method, url, headers, body, timeout_seconds))
        if self.raise_exc:
            raise RuntimeError("network_fail")
        return self.status, self.body

def test_idempotency_replays_without_second_call():
    cfg = DropiOrderForwarderConfig(base_url="https://example.test", api_token="t", max_attempts=1)
    tr = DummyTransport(status=201)
    store = InMemoryIdempotencyStore()
    fwd = DropiOrderForwarder(cfg, transport=tr, store=store)

    r1 = fwd.forward_shopify_order(ORDER, idempotency_key="k1")
    r2 = fwd.forward_shopify_order(ORDER, idempotency_key="k1")

    assert r1.ok is True
    assert r2.replayed is True
    assert len(tr.calls) == 1

def test_payload_contains_external_id_and_items():
    cfg = DropiOrderForwarderConfig(base_url="https://example.test", api_token="t", max_attempts=1)
    tr = DummyTransport(status=201)
    fwd = DropiOrderForwarder(cfg, transport=tr)

    _ = fwd.forward_shopify_order(ORDER, idempotency_key="k2")

    assert len(tr.calls) == 1
    sent_body = tr.calls[0][3].decode("utf-8")
    payload = json.loads(sent_body)
    assert payload["external_id"] == "123"
    assert payload["items"][0]["sku"] == "SKU1"
    assert payload["items"][0]["quantity"] == 2

def test_circuit_breaker_opens_after_threshold():
    cfg = DropiOrderForwarderConfig(
        base_url="https://example.test",
        api_token="t",
        max_attempts=1,
        circuit_fail_threshold=2,
        circuit_cooldown_seconds=60,
    )
    tr = DummyTransport(status=503)
    fwd = DropiOrderForwarder(cfg, transport=tr)

    r1 = fwd.forward_shopify_order(ORDER, idempotency_key="k3")
    r2 = fwd.forward_shopify_order(ORDER, idempotency_key="k4")
    assert r1.ok is False
    assert r2.ok is False

    with pytest.raises(CircuitOpenError):
        fwd.forward_shopify_order(ORDER, idempotency_key="k5")
