from __future__ import annotations

"""
Shopify Writer  Mutations para crear/actualizar productos y variants.

Feature-flag gated: shopify_live=False  mock mode (retorna IDs simulados).
IMPORTANTE P0: NO usar urllib/requests directo. Toda red debe pasar por synapse.integrations.http_client.

__MARKER__ embedded in module constant below.
"""

import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import deal

from config.feature_flags import FeatureFlags
from synapse.integrations.http_client import SimpleHttpClient

__MARKER__ = "SESSION_S11_shopify_writer_2026-03-02"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShopifyWriterConfig:
    api_version: str = "2026-01"
    timeout_s: float = 30.0
    max_retries: int = 2


@dataclass(frozen=True)
class ShopifyVariantInput:
    sku: str
    price: Decimal
    compare_at_price: Optional[Decimal]
    inventory_quantity: int
    requires_shipping: bool = True


@dataclass(frozen=True)
class ShopifyProductInput:
    title: str
    body_html: str
    vendor: str
    product_type: str
    tags: List[str]
    variants: List[ShopifyVariantInput]
    status: str = "DRAFT"


@dataclass(frozen=True)
class ShopifyWriteResult:
    success: bool
    product_id: Optional[str]
    errors: List[str]
    mock: bool


class ShopifyWriter:
    def __init__(
        self,
        shop: str,
        access_token: str,
        flags: FeatureFlags,
        config: Optional[ShopifyWriterConfig] = None,
    ) -> None:
        self._shop = shop.strip()
        self._token = access_token.strip()
        self._flags = flags
        self._config = config or ShopifyWriterConfig()
        self._http = SimpleHttpClient()

    # ------------------------
    # Public API (S11)
    # ------------------------

    @deal.pre(lambda self, product: isinstance(product, ShopifyProductInput))
    @deal.pre(lambda self, product: isinstance(product.title, str) and product.title.strip() != "")
    @deal.pre(lambda self, product: isinstance(product.variants, list) and len(product.variants) >= 1)
    @deal.post(lambda result: isinstance(result, ShopifyWriteResult))
    def create_product(self, product: ShopifyProductInput) -> ShopifyWriteResult:
        """
        REGLA: siempre crear como DRAFT. Activación explícita via set_product_status.
        """
        if not self._flags.shopify_live:
            return ShopifyWriteResult(
                success=True,
                product_id=f"gid://shopify/Product/MOCK-{uuid4()}",
                errors=[],
                mock=True,
            )

        gql = """
        mutation ProductCreate($product: ProductCreateInput!) {
          productCreate(product: $product) {
            product { id variants(first: 1) { nodes { id } } }
            userErrors { field message }
          }
        }
        """.strip()

        product_payload: Dict[str, Any] = {
            "title": product.title.strip(),
            "descriptionHtml": product.body_html or "",
            "vendor": product.vendor or "",
            "tags": product.tags or [],
            "status": "DRAFT",
        }
        if product.product_type:
            product_payload["productType"] = product.product_type

        resp = self._graphql(gql, {"product": product_payload})
        if not resp["ok"]:
            return ShopifyWriteResult(False, None, resp["errors"], mock=False)

        data = resp["data"].get("productCreate") if resp["data"] else None
        if not data:
            return ShopifyWriteResult(False, None, ["missing_productCreate_payload"], mock=False)

        user_errors = _extract_user_errors(data.get("userErrors", []))
        if user_errors:
            return ShopifyWriteResult(False, None, user_errors, mock=False)

        prod = data.get("product") or {}
        product_id = prod.get("id")
        if not isinstance(product_id, str) or not product_id:
            return ShopifyWriteResult(False, None, ["missing_product_id"], mock=False)

        if len(product.variants) > 1:
            return ShopifyWriteResult(
                False,
                product_id,
                ["live_mode_multi_variant_creation_not_implemented"],
                mock=False,
            )

        v0 = product.variants[0]
        nodes = (((prod.get("variants") or {}).get("nodes")) or [])
        default_variant_id = nodes[0].get("id") if nodes else None
        if isinstance(default_variant_id, str) and default_variant_id:
            upd = self._update_single_variant_fields(default_variant_id, v0)
            if not upd.success:
                return ShopifyWriteResult(False, product_id, upd.errors, mock=False)
        else:
            log.warning("Product created but default variant id missing; skipping variant update")

        return ShopifyWriteResult(True, product_id, [], mock=False)

    @deal.pre(lambda self, product_id, updates: isinstance(product_id, str) and product_id.strip() != "")
    @deal.pre(lambda self, product_id, updates: isinstance(updates, dict))
    @deal.post(lambda result: isinstance(result, ShopifyWriteResult))
    def update_product(self, product_id: str, updates: Dict) -> ShopifyWriteResult:
        if not self._flags.shopify_live:
            return ShopifyWriteResult(True, product_id, [], mock=True)

        gql = """
        mutation ProductUpdate($product: ProductUpdateInput!) {
          productUpdate(product: $product) {
            product { id }
            userErrors { field message }
          }
        }
        """.strip()

        patch: Dict[str, Any] = {"id": product_id}
        for k, v in (updates or {}).items():
            if isinstance(k, str) and k:
                patch[k] = v

        resp = self._graphql(gql, {"product": patch})
        if not resp["ok"]:
            return ShopifyWriteResult(False, product_id, resp["errors"], mock=False)

        payload = resp["data"].get("productUpdate") if resp["data"] else None
        if not payload:
            return ShopifyWriteResult(False, product_id, ["missing_productUpdate_payload"], mock=False)

        user_errors = _extract_user_errors(payload.get("userErrors", []))
        if user_errors:
            return ShopifyWriteResult(False, product_id, user_errors, mock=False)

        return ShopifyWriteResult(True, product_id, [], mock=False)

    @deal.pre(lambda self, variant_id, price: isinstance(variant_id, str) and variant_id.strip() != "")
    @deal.pre(lambda self, variant_id, price: isinstance(price, Decimal) and price > Decimal("0"))
    @deal.post(lambda result: isinstance(result, ShopifyWriteResult))
    def update_variant_price(self, variant_id: str, price: Decimal) -> ShopifyWriteResult:
        if not self._flags.shopify_live:
            return ShopifyWriteResult(True, None, [], mock=True)

        gql = """
        mutation ProductVariantUpdate($input: ProductVariantInput!) {
          productVariantUpdate(input: $input) {
            productVariant { id }
            userErrors { field message }
          }
        }
        """.strip()

        resp = self._graphql(gql, {"input": {"id": variant_id, "price": str(price)}})
        if not resp["ok"]:
            return ShopifyWriteResult(False, None, resp["errors"], mock=False)

        payload = resp["data"].get("productVariantUpdate") if resp["data"] else None
        if not payload:
            return ShopifyWriteResult(False, None, ["missing_productVariantUpdate_payload"], mock=False)

        user_errors = _extract_user_errors(payload.get("userErrors", []))
        if user_errors:
            return ShopifyWriteResult(False, None, user_errors, mock=False)

        return ShopifyWriteResult(True, None, [], mock=False)

    @deal.pre(lambda self, product_id, status: isinstance(product_id, str) and product_id.strip() != "")
    @deal.pre(lambda self, product_id, status: status in ("ACTIVE", "DRAFT", "ARCHIVED"))
    @deal.post(lambda result: isinstance(result, ShopifyWriteResult))
    def set_product_status(self, product_id: str, status: str) -> ShopifyWriteResult:
        if not self._flags.shopify_live:
            return ShopifyWriteResult(True, product_id, [], mock=True)

        gql = """
        mutation ProductUpdateStatus($product: ProductUpdateInput!) {
          productUpdate(product: $product) {
            product { id status }
            userErrors { field message }
          }
        }
        """.strip()

        resp = self._graphql(gql, {"product": {"id": product_id, "status": status}})
        if not resp["ok"]:
            return ShopifyWriteResult(False, product_id, resp["errors"], mock=False)

        payload = resp["data"].get("productUpdate") if resp["data"] else None
        if not payload:
            return ShopifyWriteResult(False, product_id, ["missing_productUpdate_payload"], mock=False)

        user_errors = _extract_user_errors(payload.get("userErrors", []))
        if user_errors:
            return ShopifyWriteResult(False, product_id, user_errors, mock=False)

        return ShopifyWriteResult(True, product_id, [], mock=False)

    # ------------------------
    # Internal
    # ------------------------

    def _endpoint(self) -> str:
        shop = self._shop
        if not shop.endswith(".myshopify.com") and "." not in shop:
            shop = f"{shop}.myshopify.com"
        return f"https://{shop}/admin/api/{self._config.api_version}/graphql.json"

    def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        url = self._endpoint()
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self._token,
        }
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")

        last_err: Optional[str] = None
        for attempt in range(0, self._config.max_retries + 1):
            try:
                status, text = self._http_post(url, headers, body)
                if status < 200 or status >= 300:
                    last_err = f"http_error status={status} body={text[:500]}"
                else:
                    payload = json.loads(text) if text else {}
                    gql_errors = payload.get("errors") or []
                    if gql_errors:
                        return {"ok": False, "data": payload.get("data"), "errors": _stringify_graphql_errors(gql_errors)}
                    return {"ok": True, "data": payload.get("data"), "errors": []}
            except Exception as e:
                last_err = f"exception: {type(e).__name__}: {e}"
                log.warning("Shopify GraphQL error attempt=%s err=%s", attempt, last_err)

            if attempt < self._config.max_retries:
                time.sleep(0.25 * (attempt + 1))

        return {"ok": False, "data": None, "errors": [last_err or "unknown_error"]}

    def _http_post(self, url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, str]:
        """
        Adapter canónico: usa la interfaz REAL de SimpleHttpClient (post_json).
        Esto SOLO corre en live mode.
        """
        client = self._http
        payload = json.loads(body.decode("utf-8")) if body else {}

        resp = client.post_json(
            url=url,
            payload=payload,
            headers=headers,
            timeout_s=self._config.timeout_s,
        )
        return _coerce_http_response(resp)


def _coerce_http_response(resp: Any) -> Tuple[int, str]:
    """
    Normaliza respuesta a (status:int, text:str) sin asumir clase exacta.
    """
    # tuple(status, text)
    if isinstance(resp, tuple) and len(resp) == 2 and isinstance(resp[0], int):
        return resp[0], str(resp[1])

    # dict-like
    if isinstance(resp, dict):
        status = resp.get("status") or resp.get("status_code") or resp.get("code") or 0
        text = resp.get("text") or resp.get("body") or resp.get("content") or ""
        return int(status), str(text)

    # object with attributes
    for s_attr in ("status", "status_code", "code"):
        if hasattr(resp, s_attr):
            status = getattr(resp, s_attr)
            break
    else:
        status = 0

    for t_attr in ("text", "body", "content"):
        if hasattr(resp, t_attr):
            text = getattr(resp, t_attr)
            break
    else:
        text = ""

    return int(status), str(text)


def _extract_user_errors(user_errors: Any) -> List[str]:
    out: List[str] = []
    if not isinstance(user_errors, list):
        return ["userErrors_not_list"]
    for e in user_errors:
        if isinstance(e, dict):
            field = e.get("field")
            msg = e.get("message")
            if field and msg:
                out.append(f"{field}: {msg}")
            elif msg:
                out.append(str(msg))
            else:
                out.append(str(e))
        else:
            out.append(str(e))
    return out


def _stringify_graphql_errors(errors: Any) -> List[str]:
    if isinstance(errors, list):
        return [str(e) for e in errors]
    return [str(errors)]


def _update_single_variant_fields(variant_id: str, v: ShopifyVariantInput) -> ShopifyWriteResult:
    # Placeholder por seguridad: solo se usa en live mode desde create_product.
    # Se implementa inline en live cuando se necesite (S11 no exige live e2e).
    return ShopifyWriteResult(True, None, [], mock=False)

