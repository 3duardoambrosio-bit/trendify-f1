# synapse/integration/webhooks.py
"""
Webhooks Core — OLEADA 17
========================

- Verificación HMAC SHA256 (estilo Stripe-ish)
- Router por event_type con handlers
- Payload parsing seguro (no revienta por JSON raro)

Uso:
from synapse.integration.webhooks import WebhookRouter, verify_hmac_sha256

router = WebhookRouter()
@router.on("SHOPIFY_ORDER_CREATED")
def handle(evt): ...
"""

from __future__ import annotations

import hmac
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


class WebhookError(Exception):
    pass


def verify_hmac_sha256(secret: str, payload: bytes, signature_hex: str) -> bool:
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    # compare_digest evita timing attacks
    return hmac.compare_digest(mac, (signature_hex or "").lower())


def safe_json_loads(payload: bytes) -> Dict[str, Any]:
    try:
        txt = payload.decode("utf-8", errors="replace")
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else {"_non_dict": obj}
    except Exception:
        return {"_invalid_json": True}


@dataclass(frozen=True)
class WebhookEvent:
    event_type: str
    payload: Dict[str, Any]
    raw: bytes


HandlerFn = Callable[[WebhookEvent], Any]


class WebhookRouter:
    def __init__(self):
        self._handlers: Dict[str, HandlerFn] = {}

    def on(self, event_type: str):
        def deco(fn: HandlerFn) -> HandlerFn:
            self._handlers[event_type] = fn
            return fn
        return deco

    def dispatch(self, event_type: str, payload_bytes: bytes) -> Any:
        if event_type not in self._handlers:
            raise WebhookError(f"No handler for event_type={event_type}")
        evt = WebhookEvent(event_type=event_type, payload=safe_json_loads(payload_bytes), raw=payload_bytes)
        return self._handlers[event_type](evt)

    def handlers(self) -> Dict[str, HandlerFn]:
        return dict(self._handlers)
