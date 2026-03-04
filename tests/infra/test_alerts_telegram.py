"""
S17 Tests: Telegram alert sink.

Acceptance criteria:
  1. NullAlertSink never blocks, always ok
  2. TelegramAlertSink with missing token → clean error
  3. TelegramAlertSink with valid http_client → delivered=True
  4. Rate limiting: same message within interval → skip
  5. Network policy: no urllib/requests in alerts.py
  6. Exception in http_client → never raises, returns ok=False
  7. HTTP error (4xx/5xx) → delivered=False
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from synapse.infra.alerts import (
    AlertSendResult,
    NullAlertSink,
    TelegramAlertSink,
)


# ── FakeHttp matches SimpleHttpClient.post_json() interface ──

@dataclass
class FakeHttpResponse:
    """Matches synapse.integrations.http_client.HttpResponse shape."""
    status: int
    body: bytes
    headers: Dict[str, str] = None

    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


class FakeHttpClient:
    """Fake that matches SimpleHttpClient.post_json(url, payload, headers, timeout_s)."""

    def __init__(self, status: int = 200, body: bytes = b'{"ok": true, "result": {"message_id": 1}}'):
        self.calls: list = []
        self._status = status
        self._body = body

    def post_json(
        self,
        url: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
        timeout_s: float = 20.0,
    ) -> FakeHttpResponse:
        self.calls.append({"url": url, "payload": payload, "headers": headers, "timeout_s": timeout_s})
        return FakeHttpResponse(status=self._status, body=self._body)


class FakeHttpClientRaises:
    """Simulates network failure."""

    def post_json(self, **kwargs) -> None:
        raise ConnectionError("network_down")


# ── 1. NullAlertSink ────────────────────────────────────────

class TestNullSink:
    def test_never_blocks(self):
        s = NullAlertSink()
        r = s.send("hello")
        assert r.ok is True
        assert r.delivered is False

    def test_accepts_any_level(self):
        s = NullAlertSink()
        r = s.send("test", level="CRITICAL")
        assert r.ok is True


# ── 2. Missing token/chat_id ────────────────────────────────

class TestMissingConfig:
    def test_empty_token(self):
        s = TelegramAlertSink(token="", chat_id="123")
        r = s.send("x")
        assert r.ok is False
        assert "missing_token_or_chat_id" in (r.error or "")

    def test_empty_chat_id(self):
        s = TelegramAlertSink(token="T0K", chat_id="")
        r = s.send("x")
        assert r.ok is False
        assert "missing_token_or_chat_id" in (r.error or "")

    def test_empty_text(self):
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=FakeHttpClient())
        r = s.send("")
        assert r.ok is False
        assert r.error == "invalid_text"


# ── 3. Happy path ───────────────────────────────────────────

class TestHappyPath:
    def test_send_delivers_and_returns_ok(self):
        fake = FakeHttpClient()
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=fake)
        r = s.send("vault blocked spend", level="WARN")

        assert r.ok is True
        assert r.delivered is True
        assert r.status == 200
        assert len(fake.calls) == 1

        call = fake.calls[0]
        assert "api.telegram.org" in call["url"]
        assert "botT0K" in call["url"]
        assert call["payload"]["chat_id"] == "123"
        assert "[SYNAPSE][WARN]" in call["payload"]["text"]

    def test_level_defaults_to_info(self):
        fake = FakeHttpClient()
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=fake)
        s.send("test")
        assert "[SYNAPSE][INFO]" in fake.calls[0]["payload"]["text"]


# ── 4. Rate limiting ────────────────────────────────────────

class TestRateLimit:
    def test_same_message_rate_limited(self):
        fake = FakeHttpClient()
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=fake, min_interval_s=9999)
        r1 = s.send("same")
        r2 = s.send("same")
        assert r1.delivered is True
        assert r2.delivered is False
        assert r2.error == "rate_limited"
        assert r2.ok is True  # rate_limited is not an error, just skipped
        assert len(fake.calls) == 1  # only 1 actual HTTP call

    def test_different_messages_not_rate_limited(self):
        fake = FakeHttpClient()
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=fake, min_interval_s=9999)
        r1 = s.send("msg_a")
        r2 = s.send("msg_b")
        assert r1.delivered is True
        assert r2.delivered is True
        assert len(fake.calls) == 2

    def test_explicit_dedupe_key(self):
        fake = FakeHttpClient()
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=fake, min_interval_s=9999)
        r1 = s.send("aaa", dedupe_key="k1")
        r2 = s.send("bbb", dedupe_key="k1")  # different text, same key
        assert r1.delivered is True
        assert r2.delivered is False
        assert r2.error == "rate_limited"


# ── 5. Network policy ───────────────────────────────────────

class TestNetworkPolicy:
    def test_no_urllib_no_requests_in_alerts_module(self):
        import pathlib
        p = pathlib.Path("synapse/infra/alerts.py").read_text(encoding="utf-8")
        # Must not import urllib or requests directly
        assert "import urllib" not in p
        assert "import requests" not in p
        assert "from urllib" not in p
        assert "from requests" not in p


# ── 6. Exception → never raises ─────────────────────────────

class TestNeverRaises:
    def test_http_client_exception_returns_ok_false(self):
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=FakeHttpClientRaises())
        r = s.send("test")
        assert r.ok is False
        assert r.delivered is False
        assert "exception:ConnectionError" in (r.error or "")


# ── 7. HTTP error codes ─────────────────────────────────────

class TestHttpErrors:
    def test_4xx_returns_not_delivered(self):
        fake = FakeHttpClient(status=401, body=b'{"ok": false, "description": "Unauthorized"}')
        s = TelegramAlertSink(token="BAD", chat_id="123", http_client=fake)
        r = s.send("test")
        assert r.ok is False
        assert r.delivered is False
        assert r.status == 401

    def test_5xx_returns_not_delivered(self):
        fake = FakeHttpClient(status=500, body=b"Internal Server Error")
        s = TelegramAlertSink(token="T0K", chat_id="123", http_client=fake)
        r = s.send("test")
        assert r.ok is False
        assert r.delivered is False
        assert r.status == 500
