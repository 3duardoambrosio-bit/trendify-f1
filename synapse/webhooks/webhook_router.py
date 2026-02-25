# synapse/webhooks/webhook_router.py
"""
Webhook Router (genérico) para SYNAPSE.

Objetivo:
- Verificar firmas HMAC (cuando aplique).
- Enrutar eventos por "provider" y "event_type".
- Mantenerlo simple: aún no levantamos server; esto es core reusable.

Seguridad:
- Signature invalid => se rechaza.
"""

from __future__ import annotations

import hmac
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


class WebhookError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebhookEvent:
    provider: str
    event_type: str
    payload: Dict[str, Any]
    raw_body: bytes


def compute_hmac_sha256(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return mac


def verify_hmac_sha256(secret: str, body: bytes, signature_hex: str) -> bool:
    expected = compute_hmac_sha256(secret, body)
    return hmac.compare_digest(expected, (signature_hex or "").strip().lower())


Handler = Callable[[WebhookEvent], Dict[str, Any]]


class WebhookRouter:
    def __init__(self):
        self._handlers: Dict[Tuple[str, str], Handler] = {}

    def register(self, provider: str, event_type: str, handler: Handler) -> None:
        key = (provider.strip().lower(), event_type.strip().lower())
        self._handlers[key] = handler

    def handle(
        self,
        *,
        provider: str,
        event_type: str,
        raw_body: bytes,
        secret: Optional[str] = None,
        signature_hex: Optional[str] = None,
    ) -> Dict[str, Any]:
        prov = provider.strip().lower()
        et = event_type.strip().lower()

        if secret is not None:
            if not signature_hex:
                raise WebhookError("missing signature")
            if not verify_hmac_sha256(secret, raw_body, signature_hex):
                raise WebhookError("invalid signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, TypeError) as e:
            raise WebhookError("invalid json body") from e

        key = (prov, et)
        if key not in self._handlers:
            raise WebhookError(f"no handler for {prov}:{et}")

        ev = WebhookEvent(provider=prov, event_type=et, payload=payload, raw_body=raw_body)
        return self._handlers[key](ev)