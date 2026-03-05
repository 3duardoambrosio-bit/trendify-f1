"""
S17+S19 — Alert Sinks (Telegram + Null).

Design:
- AlertSink protocol: .send(text, level, dedupe_key) → AlertSendResult
- NullAlertSink: no-op, never blocks, always ok
- TelegramAlertSink: best-effort via SimpleHttpClient.post_json()

CRITICAL:
  - Alerting NEVER raises. If Telegram is down, log + return ok=False.
  - NO urllib/requests in this module. All network via SimpleHttpClient.
  - Rate limiting: same dedupe_key within min_interval_s → skip.
  - S19: _last_sent capped at max_rate_limit_keys (default 1000). FIFO eviction.

__MARKER__ embedded in module constant below.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

__MARKER__ = "SESSION_S19_telegram_alerts_2026-03-04"

log = logging.getLogger(__name__)

_DEFAULT_MAX_RATE_KEYS = 1000


@dataclass(frozen=True)
class AlertSendResult:
    ok: bool
    delivered: bool
    status: int
    error: Optional[str]


class AlertSink(Protocol):
    def send(self, text: str, *, level: str = "INFO", dedupe_key: Optional[str] = None) -> AlertSendResult: ...


class NullAlertSink:
    """No-op sink. Always ok, never delivers. For tests and dry-run."""

    def send(self, text: str, *, level: str = "INFO", dedupe_key: Optional[str] = None) -> AlertSendResult:
        return AlertSendResult(ok=True, delivered=False, status=0, error=None)


class TelegramAlertSink:
    """
    Best-effort Telegram alerts via SimpleHttpClient.post_json().

    Uses the REAL SimpleHttpClient interface:
      client.post_json(url, payload, headers, timeout_s) → HttpResponse
      HttpResponse.status: int
      HttpResponse.body: bytes

    S19: _last_sent capped at max_rate_limit_keys. When full, evicts oldest entries (FIFO).
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        timeout_s: float = 10.0,
        min_interval_s: float = 15.0,
        max_rate_limit_keys: int = _DEFAULT_MAX_RATE_KEYS,
        http_client: Optional[Any] = None,
    ) -> None:
        self._token = (token or "").strip()
        self._chat_id = (chat_id or "").strip()
        self._timeout_s = float(timeout_s)
        self._min_interval_s = float(min_interval_s)
        self._max_keys = max(1, max_rate_limit_keys)
        self._last_sent: Dict[str, float] = {}
        self._http = http_client

    def _client(self) -> Any:
        if self._http is not None:
            return self._http
        from synapse.integrations.http_client import SimpleHttpClient  # type: ignore
        self._http = SimpleHttpClient()
        return self._http

    def _url(self) -> str:
        return f"https://api.telegram.org/bot{self._token}/sendMessage"

    def _evict_oldest(self) -> None:
        """Evict oldest entries when _last_sent exceeds max_keys."""
        if len(self._last_sent) <= self._max_keys:
            return
        # Sort by timestamp, keep newest max_keys
        sorted_keys = sorted(self._last_sent.keys(), key=lambda k: self._last_sent[k])
        to_remove = len(self._last_sent) - self._max_keys
        for k in sorted_keys[:to_remove]:
            del self._last_sent[k]

    def send(self, text: str, *, level: str = "INFO", dedupe_key: Optional[str] = None) -> AlertSendResult:
        try:
            return self._send_inner(text, level=level, dedupe_key=dedupe_key)
        except Exception as e:
            # NEVER raise from alerting
            log.exception("telegram_alert_sink_unhandled")
            return AlertSendResult(ok=False, delivered=False, status=0, error=f"exception:{type(e).__name__}:{e}")

    def _send_inner(self, text: str, *, level: str, dedupe_key: Optional[str]) -> AlertSendResult:
        if not isinstance(text, str) or text.strip() == "":
            return AlertSendResult(ok=False, delivered=False, status=0, error="invalid_text")

        if self._token == "" or self._chat_id == "":
            return AlertSendResult(ok=False, delivered=False, status=0, error="missing_token_or_chat_id")

        # Rate limiting by dedupe_key
        key = dedupe_key or hashlib.sha256(text.encode("utf-8")).hexdigest()
        now = time.time()
        last = self._last_sent.get(key)
        if last is not None and (now - last) < self._min_interval_s:
            return AlertSendResult(ok=True, delivered=False, status=0, error="rate_limited")

        self._last_sent[key] = now
        self._evict_oldest()

        # Build Telegram sendMessage payload
        tg_payload = {
            "chat_id": self._chat_id,
            "text": f"[SYNAPSE][{level}] {text}",
            "disable_web_page_preview": True,
        }

        # Use SimpleHttpClient.post_json() — the REAL interface
        client = self._client()
        resp = client.post_json(
            url=self._url(),
            payload=tg_payload,
            timeout_s=self._timeout_s,
        )

        # HttpResponse has .status (int) and .body (bytes)
        status = resp.status
        body_bytes = getattr(resp, "body", b"")
        body_text = body_bytes.decode("utf-8", errors="replace") if isinstance(body_bytes, bytes) else str(body_bytes)

        if status < 200 or status >= 300:
            return AlertSendResult(ok=False, delivered=False, status=status, error=f"http_{status}:{body_text[:200]}")

        # Telegram responds {"ok": true, ...}
        try:
            j = json.loads(body_text) if body_text else {}
            if isinstance(j, dict) and j.get("ok") is True:
                return AlertSendResult(ok=True, delivered=True, status=status, error=None)
            return AlertSendResult(ok=False, delivered=False, status=status, error=f"telegram_not_ok:{str(j)[:200]}")
        except Exception:
            return AlertSendResult(ok=False, delivered=False, status=status, error="response_parse_failed")
