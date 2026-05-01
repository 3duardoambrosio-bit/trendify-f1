from __future__ import annotations

import json
import pytest

from synapse.integrations.dropi import order_forwarder as m
from synapse.integrations.dropi.order_forwarder import (
    CircuitOpenError,
    DropiOrderForwarder,
    DropiOrderForwarderConfig,
    InMemoryIdempotencyStore,
)

ORDER = {
    "id": 123,
    "currency": "MXN",
    "email": "lalo@example.com",
    "customer": {"email": "lalo@example.com", "first_name": "Lalo", "last_name": "ACERO"},
    "shipping_address": {
        "name": "Lalo",
        "address1": "Calle 1",
        "city": "CDMX",
        "zip": "00000",
        "country": "MX",
    },
    "line_items": [{"sku": "SKU1", "title": "Prod 1", "quantity": 2, "price": "99.50"}],
    "total_price": "199.00",
}


class DummyTransport:
    def __init__(self, *, responses=None):
        self.calls = []
        self.responses = list(responses or [(201, b'{"ok":true}')])

    def request(self, method, url, headers, body, timeout_seconds):
        self.calls.append((method, url, headers, body, timeout_seconds))
        if not self.responses:
            raise AssertionError("No more scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def test_idempotency_replays_without_second_call():
    cfg = DropiOrderForwarderConfig(base_url="https://example.test", api_token="t", max_attempts=1)
    tr = DummyTransport(responses=[(201, b'{"ok":true}')])
    store = InMemoryIdempotencyStore()
    fwd = DropiOrderForwarder(cfg, transport=tr, store=store)

    r1 = fwd.forward_shopify_order(ORDER, idempotency_key="k1")
    r2 = fwd.forward_shopify_order(ORDER, idempotency_key="k1")

    assert r1.ok is True
    assert r2.replayed is True
    assert len(tr.calls) == 1


def test_payload_contains_external_id_items_headers_url_and_timeout():
    cfg = DropiOrderForwarderConfig(
        base_url="https://example.test",
        api_token="tok_123",
        timeout_seconds=17,
        max_attempts=1,
        user_agent="synapse-dropi-forwarder/test",
    )
    tr = DummyTransport(responses=[(201, b'{"ok":true}')])
    fwd = DropiOrderForwarder(cfg, transport=tr)

    result = fwd.forward_shopify_order(ORDER, idempotency_key="k2")

    assert result.ok is True
    assert len(tr.calls) == 1

    method, url, headers, body, timeout_seconds = tr.calls[0]
    payload = json.loads(body.decode("utf-8"))

    assert method == "POST"
    assert url == "https://example.test/orders"
    assert timeout_seconds == 17
    assert headers["Authorization"] == "Bearer tok_123"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["User-Agent"] == "synapse-dropi-forwarder/test"
    assert headers["X-Idempotency-Key"] == "k2"
    assert payload["external_id"] == "123"
    assert payload["items"][0]["sku"] == "SKU1"
    assert payload["items"][0]["quantity"] == 2


def test_retries_on_5xx_until_success_with_incremental_backoff(monkeypatch):
    cfg = DropiOrderForwarderConfig(
        base_url="https://example.test",
        api_token="t",
        max_attempts=3,
        backoff_seconds=0.5,
    )
    tr = DummyTransport(
        responses=[
            (503, b"upstream_1"),
            (502, b"upstream_2"),
            (201, b'{"ok":true}'),
        ]
    )
    fwd = DropiOrderForwarder(cfg, transport=tr)

    sleep_calls = []
    monkeypatch.setattr(m.time, "sleep", lambda s: sleep_calls.append(s))

    result = fwd.forward_shopify_order(ORDER, idempotency_key="k3")

    assert result.ok is True
    assert result.status_code == 201
    assert len(tr.calls) == 3
    assert sleep_calls == [0.5, 1.0]
    assert fwd._fail_count == 0


def test_4xx_does_not_retry_and_failed_result_is_cached():
    cfg = DropiOrderForwarderConfig(
        base_url="https://example.test",
        api_token="t",
        max_attempts=3,
    )
    tr = DummyTransport(responses=[(400, b"bad_request")])
    store = InMemoryIdempotencyStore()
    fwd = DropiOrderForwarder(cfg, transport=tr, store=store)

    r1 = fwd.forward_shopify_order(ORDER, idempotency_key="k4")
    r2 = fwd.forward_shopify_order(ORDER, idempotency_key="k4")

    assert r1.ok is False
    assert r1.status_code == 400
    assert r1.replayed is False
    assert r2.ok is False
    assert r2.status_code == 400
    assert r2.replayed is True
    assert len(tr.calls) == 1


def test_circuit_breaker_opens_after_threshold():
    cfg = DropiOrderForwarderConfig(
        base_url="https://example.test",
        api_token="t",
        max_attempts=1,
        circuit_fail_threshold=2,
        circuit_cooldown_seconds=60,
    )
    tr = DummyTransport(responses=[(503, b"e1"), (503, b"e2")])
    fwd = DropiOrderForwarder(cfg, transport=tr)

    r1 = fwd.forward_shopify_order(ORDER, idempotency_key="k5")
    r2 = fwd.forward_shopify_order(ORDER, idempotency_key="k6")

    assert r1.ok is False
    assert r2.ok is False

    with pytest.raises(CircuitOpenError):
        fwd.forward_shopify_order(ORDER, idempotency_key="k7")


def test_transport_exception_bubbles_and_does_not_cache():
    cfg = DropiOrderForwarderConfig(base_url="https://example.test", api_token="t", max_attempts=3)
    tr = DummyTransport(responses=[RuntimeError("network_fail"), RuntimeError("network_fail")])
    store = InMemoryIdempotencyStore()
    fwd = DropiOrderForwarder(cfg, transport=tr, store=store)

    with pytest.raises(RuntimeError, match="network_fail"):
        fwd.forward_shopify_order(ORDER, idempotency_key="k8")

    with pytest.raises(RuntimeError, match="network_fail"):
        fwd.forward_shopify_order(ORDER, idempotency_key="k8")

    assert len(tr.calls) == 2
    assert store.get("k8") is None


def test_success_resets_fail_count_after_prior_failure():
    cfg = DropiOrderForwarderConfig(base_url="https://example.test", api_token="t", max_attempts=1)
    tr = DummyTransport(responses=[(503, b"temporary"), (201, b'{"ok":true}')])
    fwd = DropiOrderForwarder(cfg, transport=tr)

    r1 = fwd.forward_shopify_order(ORDER, idempotency_key="k9")
    assert r1.ok is False
    assert fwd._fail_count == 1

    r2 = fwd.forward_shopify_order(ORDER, idempotency_key="k10")
    assert r2.ok is True
    assert fwd._fail_count == 0
