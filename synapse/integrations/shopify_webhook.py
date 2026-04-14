from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Mapping, MutableSet, Optional


def _get_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    n = name.lower()
    for k, v in headers.items():
        if k.lower() == n:
            return v
    return None


@dataclass(frozen=True)
class ShopifyWebhookHeaders:
    hmac_b64: Optional[str]
    webhook_id: Optional[str]
    topic: Optional[str]
    shop_domain: Optional[str]


def extract_shopify_webhook_headers(headers: Mapping[str, str]) -> ShopifyWebhookHeaders:
    return ShopifyWebhookHeaders(
        hmac_b64=_get_header(headers, "X-Shopify-Hmac-Sha256"),
        webhook_id=_get_header(headers, "X-Shopify-Webhook-Id"),
        topic=_get_header(headers, "X-Shopify-Topic"),
        shop_domain=_get_header(headers, "X-Shopify-Shop-Domain"),
    )


def build_shopify_dedup_key(shop_domain: Optional[str], webhook_id: Optional[str]) -> Optional[str]:
    shop = (shop_domain or "").strip()
    wid = (webhook_id or "").strip()
    if shop and wid:
        return f"{shop}:{wid}"
    if wid:
        return wid
    return None


def compute_shopify_hmac_sha256_base64(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")


def verify_shopify_hmac_sha256(secret: str, body: bytes, header_hmac_b64: Optional[str]) -> bool:
    if not secret or not secret.strip():
        raise ValueError("shopify_webhook_secret_required")
    if not header_hmac_b64:
        return False
    expected = compute_shopify_hmac_sha256_base64(secret, body)
    return hmac.compare_digest(expected, header_hmac_b64.strip())


@dataclass(frozen=True)
class ShopifyWebhookEvent:
    webhook_id: Optional[str]
    topic: Optional[str]
    shop_domain: Optional[str]
    dedup_key: Optional[str]
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
    if not secret or not secret.strip():
        raise ValueError("shopify_webhook_secret_required")

    parsed_headers = extract_shopify_webhook_headers(headers)
    if not verify_shopify_hmac_sha256(secret, body, parsed_headers.hmac_b64):
        return ShopifyWebhookResult(False, 401, "invalid_hmac", None)
    if not body:
        return ShopifyWebhookResult(False, 400, "empty_body", None)

    webhook_id = (parsed_headers.webhook_id or "").strip()
    if webhook_id == "":
        return ShopifyWebhookResult(False, 400, "missing_webhook_id", None)

    topic = (parsed_headers.topic or "").strip() or None
    shop_domain = (parsed_headers.shop_domain or "").strip() or None
    dedup_key = build_shopify_dedup_key(shop_domain, webhook_id)

    if dedup_set is not None and dedup_key:
        if dedup_key in dedup_set:
            return ShopifyWebhookResult(False, 409, "duplicate_webhook", None)
        dedup_set.add(dedup_key)

    try:
        payload: Any = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return ShopifyWebhookResult(False, 400, "invalid_json", None)

    ev = ShopifyWebhookEvent(
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        dedup_key=dedup_key,
        payload=payload,
        raw_body=body,
    )
    return ShopifyWebhookResult(True, 200, "ok", ev)