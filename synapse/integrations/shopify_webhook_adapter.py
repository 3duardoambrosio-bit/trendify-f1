from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableSet, Optional

from synapse.integrations.shopify_webhook import ShopifyWebhookResult, process_shopify_webhook


@dataclass(frozen=True)
class ShopifyWebhookHTTPResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    # Para consumo interno (si lo quieres loggear/encolar aguas abajo)
    result: ShopifyWebhookResult


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def handle_shopify_webhook_http(
    *,
    secret: str,
    headers: Mapping[str, str],
    body: bytes,
    dedup_set: Optional[MutableSet[str]] = None,
    on_accepted: Optional[Callable[[ShopifyWebhookResult], None]] = None,
) -> ShopifyWebhookHTTPResponse:
    """
    Adapter HTTP framework-agnostic.

    - No frameworks.
    - No network.
    - Returns: status_code + JSON body + minimal headers.
    - Optional callback on accepted (para encolar/loggear afuera).
    """
    r = process_shopify_webhook(secret=secret, headers=headers, body=body, dedup_set=dedup_set)

    if not r.accepted:
        payload = {"ok": False, "reason": r.reason}
        return ShopifyWebhookHTTPResponse(
            status_code=r.status_code,
            headers={
                "content-type": "application/json; charset=utf-8",
                "x-synapse-reason": r.reason,
            },
            body=_json_bytes(payload),
            result=r,
        )

    # Accepted
    if on_accepted is not None:
        on_accepted(r)

    payload = {
        "ok": True,
        "reason": r.reason,
        "webhook_id": (r.event.webhook_id if r.event else None),
        "topic": (r.event.topic if r.event else None),
        "shop_domain": (r.event.shop_domain if r.event else None),
    }
    return ShopifyWebhookHTTPResponse(
        status_code=r.status_code,
        headers={
            "content-type": "application/json; charset=utf-8",
            "x-synapse-reason": r.reason,
        },
        body=_json_bytes(payload),
        result=r,
    )