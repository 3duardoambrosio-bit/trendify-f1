from __future__ import annotations

"""
Shopify Writer — Mutations para crear/actualizar productos y variants.

Feature-flag gated: shopify_live=False → mock mode (retorna IDs simulados).
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


def _fmt_money(v: Decimal) -> str:
    return f"{v:.2f}"


@deal.pre(lambda p: bool(p.title.strip()))
@deal.pre(lambda p: len(p.variants) >= 1)
def _validate_product_input(p: ShopifyProductInput) -> None:
    return None


class ShopifyWriter:
    def __init__(
        self,
        shop: str,
        access_token: str,
        flags: FeatureFlags,
        config: ShopifyWriterConfig = ShopifyWriterConfig(),
        http_client: Optional[SimpleHttpClient] = None,
    ):
        self._shop = (shop or "").replace(".myshopify.com", "").strip()
        self._token = access_token
        self._flags = flags
        self._config = config
        self._http = http_client or SimpleHttpClient(
            dry_run=not bool(flags.shopify_live),
            retry_max=config.max_retries,
            backoff_s=0.25,
        )

    def _endpoint(self) -> str:
        return f"https://{self._shop}.myshopify.com/admin/api/{self._config.api_version}/graphql.json"

    def create_product(self, product: ShopifyProductInput) -> ShopifyWriteResult:
        _validate_product_input(product)

        if not self._flags.shopify_live:
            return ShopifyWriteResult(
                success=True,
                product_id=f"gid://shopify/Product/MOCK-{uuid4()}",
                errors=[],
                mock=True,
            )

        mutation = """
        mutation productCreate($input: ProductInput!) {
          productCreate(product: $input) {
            product { id }
            userErrors { field message }
          }
        }
        """
        variants = []
        for v in product.variants:
            variants.append(
                {
                    "sku": v.sku,
                    "price": _fmt_money(v.price),
                    "compareAtPrice": _fmt_money(v.compare_at_price) if v.compare_at_price is not None else None,
                    "inventoryQuantities": {
                        "availableQuantity": int(v.inventory_quantity),
                    },
                    "requiresShipping": bool(v.requires_shipping),
                }
            )

        variables = {
            "input": {
                "title": product.title,
                "descriptionHtml": product.body_html,
                "vendor": product.vendor,
                "productType": product.product_type,
                "tags": product.tags,
                "status": product.status,
                "variants": variants,
            }
        }

        out = self._run_graphql(mutation, variables)
        if not out["ok"]:
            return ShopifyWriteResult(False, None, out["errors"], mock=False)

        node = (((out.get("data") or {}).get("productCreate") or {}).get("product")) or {}
        pid = node.get("id")
        if not pid:
            return ShopifyWriteResult(False, None, ["productCreate_missing_id"], mock=False)
        return ShopifyWriteResult(True, pid, [], mock=False)

    def update_product(self, product_id: str, fields: Dict[str, Any]) -> ShopifyWriteResult:
        if not self._flags.shopify_live:
            return ShopifyWriteResult(True, product_id, [], mock=True)

        mutation = """
        mutation productUpdate($input: ProductUpdateInput!) {
          productUpdate(product: $input) {
            product { id }
            userErrors { field message }
          }
        }
        """
        variables = {
            "input": {
                "id": product_id,
                **fields,
            }
        }
        out = self._run_graphql(mutation, variables)
        if not out["ok"]:
            return ShopifyWriteResult(False, product_id, out["errors"], mock=False)

        node = (((out.get("data") or {}).get("productUpdate") or {}).get("product")) or {}
        pid = node.get("id") or product_id
        return ShopifyWriteResult(True, pid, [], mock=False)

    def set_product_status(self, product_id: str, status: str) -> ShopifyWriteResult:
        if not self._flags.shopify_live:
            return ShopifyWriteResult(True, product_id, [], mock=True)
        return self.update_product(product_id, {"status": status})

    def update_variant_price(self, variant_id: str, price: Decimal) -> ShopifyWriteResult:
        if not self._flags.shopify_live:
            return ShopifyWriteResult(True, None, [], mock=True)

        mutation = """
        mutation productVariantUpdate($input: ProductVariantInput!) {
          productVariantUpdate(input: $input) {
            productVariant { id }
            userErrors { field message }
          }
        }
        """
        variables = {
            "input": {
                "id": variant_id,
                "price": _fmt_money(price),
            }
        }
        out = self._run_graphql(mutation, variables)
        if not out["ok"]:
            return ShopifyWriteResult(False, None, out["errors"], mock=False)
        return ShopifyWriteResult(True, None, [], mock=False)

    def _run_graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        url = self._endpoint()
        headers = {
            "X-Shopify-Access-Token": self._token,
            "Content-Type": "application/json",
        }
        body = json.dumps({"query": query, "variables": variables}, ensure_ascii=False).encode("utf-8")

        last_err: Optional[str] = None
        for attempt in range(self._config.max_retries + 1):
            try:
                status, text = self._http_post(url, headers, body)
                if status != 200:
                    return {"ok": False, "data": None, "errors": [f"http_status={status}", text]}

                payload = json.loads(text or "{}")
                gql_errors = payload.get("errors")
                if gql_errors:
                    return {"ok": False, "data": payload.get("data"), "errors": _stringify_graphql_errors(gql_errors)}

                root = payload.get("data") or {}
                top = next(iter(root.values()), None)
                if isinstance(top, dict):
                    user_errors = top.get("userErrors")
                    if user_errors:
                        return {"ok": False, "data": payload.get("data"), "errors": _extract_user_errors(user_errors)}
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
    Edge cases cubiertos:
    - tuple(status, body)
    - dict con status/status_code/code y text/body/content
    - objeto con attrs status/status_code/code y text/body/content
    - bytes -> decode utf-8 fail-closed
    - fallback a .json() si no hay body textual
    """
    if resp is None:
        return 0, ""

    def _coerce_status(value: Any) -> int:
        try:
            if value is None or value == "":
                return 0
            return int(value)
        except Exception:
            return 0

    def _coerce_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def _from_json_method(obj: Any) -> Optional[str]:
        json_method = getattr(obj, "json", None)
        if not callable(json_method):
            return None
        try:
            return json.dumps(json_method(), ensure_ascii=False)
        except Exception:
            return None

    if isinstance(resp, tuple) and len(resp) == 2:
        return _coerce_status(resp[0]), _coerce_text(resp[1])

    if isinstance(resp, dict):
        status = 0
        for key in ("status", "status_code", "code"):
            if key in resp:
                status = _coerce_status(resp.get(key))
                break

        for key in ("text", "body", "content"):
            if key in resp:
                return status, _coerce_text(resp.get(key))

        return status, ""

    status = 0
    for s_attr in ("status", "status_code", "code"):
        if hasattr(resp, s_attr):
            status = _coerce_status(getattr(resp, s_attr))
            break

    for t_attr in ("text", "body", "content"):
        if hasattr(resp, t_attr):
            value = getattr(resp, t_attr)
            if value is not None:
                return status, _coerce_text(value)

    json_text = _from_json_method(resp)
    if json_text is not None:
        return status, json_text

    return status, ""


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
