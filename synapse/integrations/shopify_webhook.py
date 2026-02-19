from __future__ import annotations

import base64
import hmac
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, MutableSet, Optional


def _get_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    n = name.lower()
    for k, v in headers.items():
        if k.lower() == n:
            return v
    return None


def compute_shopify_hmac_sha256_base64(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")


def verify_shopify_hmac_sha256(secret: str, body: bytes, header_hmac_b64: Optional[str]) -> bool:
    if not header_hmac_b64:
        return False
    expected = compute_shopify_hmac_sha256_base64(secret, body)
    return hmac.compare_digest(expected, header_hmac_b64.strip())


@dataclass(frozen=True)
class ShopifyWebhookEvent:
    webhook_id: Optional[str]
    topic: Optional[str]
    shop_domain: Optional[str]
    payload: Any
    raw_body: bytes


@dataclass(frozen=True)
class ShopifyWebhookResult:
    accepted: bool
    status_code: int
    reason: str
    event: Optional[ShopifyWebhookEvent]


def process_shopify_webhook(
    *,
    secret: str,
    headers: Mapping[str, str],
    body: bytes,
    dedup_set: Optional[MutableSet[str]] = None,
) -> ShopifyWebhookResult:
    hmac_b64 = _get_header(headers, "X-Shopify-Hmac-Sha256")
    if not verify_shopify_hmac_sha256(secret, body, hmac_b64):
        return ShopifyWebhookResult(False, 401, "invalid_hmac", None)

    webhook_id = _get_header(headers, "X-Shopify-Webhook-Id")
    if dedup_set is not None and webhook_id:
        if webhook_id in dedup_set:
            return ShopifyWebhookResult(False, 409, "duplicate_webhook", None)
        dedup_set.add(webhook_id)

    topic = _get_header(headers, "X-Shopify-Topic")
    shop_domain = _get_header(headers, "X-Shopify-Shop-Domain")

    payload: Any = None
    if body:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, TypeError):
            payload = {"_parse_error": "invalid_json"}

    ev = ShopifyWebhookEvent(
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        payload=payload,
        raw_body=body,
    )
    return ShopifyWebhookResult(True, 200, "ok", ev)
