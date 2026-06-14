from __future__ import annotations

"""
Shopify Writer — Mutations para crear/actualizar productos y variants.

Feature-flag gated: shopify_live=False → mock mode (retorna IDs simulados).
IMPORTANTE P0: NO usar urllib/requests directo. Toda red debe pasar por synapse.integrations.http_client.

__MARKER__ embedded in module constant below.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

import deal

from config.feature_flags import FeatureFlags
from infra.idempotency import execute_once
from infra.network_guard import enforce_url_policy
from synapse.integrations.http_client import SimpleHttpClient

__MARKER__ = "SESSION_S11_shopify_writer_2026-03-02"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShopifyWriterConfig:
    api_version: str = "2026-01"
    timeout_s: float = 30.0
    max_retries: int = 2
    idempotency_db_path: Path = Path("runtime/idempotency/shopify_writer.sqlite3")
    idempotency_ttl_seconds: int = 3600


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


class ShopifyOperationError(RuntimeError):
    def __init__(self, errors: List[str]):
        cleaned = [str(e) for e in errors if str(e).strip()]
        self.errors = cleaned or ["shopify_operation_error"]
        super().__init__(" | ".join(self.errors))


def _fmt_money(v: Decimal) -> str:
    return f"{v:.2f}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _product_variants_payload(variants: List[ShopifyVariantInput]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for variant in variants:
        payload.append(
            {
                "sku": variant.sku,
                "price": _fmt_money(variant.price),
                "compareAtPrice": _fmt_money(variant.compare_at_price) if variant.compare_at_price is not None else None,
                "inventoryQuantities": {
                    "availableQuantity": int(variant.inventory_quantity),
                },
                "requiresShipping": bool(variant.requires_shipping),
            }
        )
    return payload


def _product_create_variables(product: ShopifyProductInput) -> Dict[str, Any]:
    return {
        "input": {
            "title": product.title,
            "descriptionHtml": product.body_html,
            "vendor": product.vendor,
            "productType": product.product_type,
            "tags": list(product.tags),
            "status": product.status,
            "variants": _product_variants_payload(product.variants),
        }
    }


def _write_idempotency_key(
    *,
    shop: str,
    api_version: str,
    operation: str,
    scope: str,
    variables: Dict[str, Any],
) -> str:
    digest = hashlib.sha256(
        _canonical_json(
            {
                "shop": shop,
                "api_version": api_version,
                "operation": operation,
                "scope": scope,
                "variables": variables,
            }
        ).encode("utf-8")
    ).hexdigest()
    return f"shopify:{operation}:{shop}:{scope}:{digest}"


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
        variables = _product_create_variables(product)
        idem_key = _write_idempotency_key(
            shop=self._shop,
            api_version=self._config.api_version,
            operation="create_product",
            scope="product",
            variables=variables,
        )
        result = self._execute_idempotent_write(
            operation_name="create_product",
            idempotency_key=idem_key,
            mutation=mutation,
            variables=variables,
            extractor=lambda out: self._extract_create_product_response(out),
        )
        return ShopifyWriteResult(
            success=result["success"],
            product_id=result.get("product_id"),
            errors=result["errors"],
            mock=False,
        )

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
        idem_key = _write_idempotency_key(
            shop=self._shop,
            api_version=self._config.api_version,
            operation="update_product",
            scope=product_id,
            variables=variables,
        )
        result = self._execute_idempotent_write(
            operation_name="update_product",
            idempotency_key=idem_key,
            mutation=mutation,
            variables=variables,
            extractor=lambda out: self._extract_update_product_response(out, fallback_product_id=product_id),
        )
        return ShopifyWriteResult(
            success=result["success"],
            product_id=result.get("product_id"),
            errors=result["errors"],
            mock=False,
        )

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
        idem_key = _write_idempotency_key(
            shop=self._shop,
            api_version=self._config.api_version,
            operation="update_variant_price",
            scope=variant_id,
            variables=variables,
        )
        result = self._execute_idempotent_write(
            operation_name="update_variant_price",
            idempotency_key=idem_key,
            mutation=mutation,
            variables=variables,
            extractor=lambda out: self._extract_update_variant_price_response(out, variant_id=variant_id),
        )
        return ShopifyWriteResult(
            success=result["success"],
            product_id=result.get("product_id"),
            errors=result["errors"],
            mock=False,
        )

    def _execute_idempotent_write(
        self,
        *,
        operation_name: str,
        idempotency_key: str,
        mutation: str,
        variables: Dict[str, Any],
        extractor: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        def _operation(_: Dict[str, Any]) -> Dict[str, Any]:
            out = self._run_graphql(
                mutation,
                variables,
                allow_retries=False,
                extra_headers={"X-Idempotency-Key": idempotency_key},
            )
            if not out["ok"]:
                raise ShopifyOperationError(out["errors"])
            return extractor(out)

        try:
            idem_result = execute_once(
                key=idempotency_key,
                payload={
                    "operation": f"shopify.{operation_name}",
                    "shop": self._shop,
                    "api_version": self._config.api_version,
                    "variables": variables,
                },
                operation=_operation,
                db_path=self._config.idempotency_db_path,
                ttl_seconds=self._config.idempotency_ttl_seconds,
            )
        except ShopifyOperationError as exc:
            return {"success": False, "product_id": None, "errors": exc.errors}
        except Exception as exc:
            return {
                "success": False,
                "product_id": None,
                "errors": [f"idempotency_execution_error:{type(exc).__name__}"],
            }

        status = str(idem_result.get("status") or "").strip().upper()
        response = idem_result.get("response")
        response_dict = dict(response) if isinstance(response, dict) else {}

        if status in {"COMPLETED", "DUPLICATE"}:
            return {
                "success": True,
                "product_id": response_dict.get("product_id"),
                "errors": [],
            }
        if status == "CONFLICT":
            return {"success": False, "product_id": None, "errors": ["idempotency_conflict"]}
        if status == "IN_FLIGHT":
            return {"success": False, "product_id": None, "errors": ["idempotency_in_flight"]}
        return {
            "success": False,
            "product_id": None,
            "errors": [f"idempotency_unexpected_status:{status or '<empty>'}"],
        }

    def _extract_create_product_response(self, out: Dict[str, Any]) -> Dict[str, Any]:
        node = (((out.get("data") or {}).get("productCreate") or {}).get("product")) or {}
        pid = node.get("id")
        if not pid:
            raise ShopifyOperationError(["productCreate_missing_id"])
        return {"product_id": str(pid)}

    def _extract_update_product_response(self, out: Dict[str, Any], *, fallback_product_id: str) -> Dict[str, Any]:
        node = (((out.get("data") or {}).get("productUpdate") or {}).get("product")) or {}
        pid = node.get("id") or fallback_product_id
        return {"product_id": str(pid)}

    def _extract_update_variant_price_response(self, out: Dict[str, Any], *, variant_id: str) -> Dict[str, Any]:
        node = (((out.get("data") or {}).get("productVariantUpdate") or {}).get("productVariant")) or {}
        vid = node.get("id") or variant_id
        return {"variant_id": str(vid)}

    def _run_graphql(
        self,
        query: str,
        variables: Dict[str, Any],
        *,
        allow_retries: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = self._endpoint()
        headers = {
            "X-Shopify-Access-Token": self._token,
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        body = json.dumps({"query": query, "variables": variables}, ensure_ascii=False).encode("utf-8")

        last_err: Optional[str] = None
        max_attempts = (self._config.max_retries + 1) if allow_retries else 1
        for attempt in range(max_attempts):
            try:
                status, text = self._http_post(url, headers, body)
                if status != 200:
                    return {"ok": False, "data": None, "errors": [f"http_status={status}", text]}

                payload = json.loads(text or "{}")
                gql_errors = payload.get("errors")
                if gql_errors:
                    return {"ok": False, "data": payload.get("data"), "errors": _stringify_graphql_errors(gql_errors)}

                root = payload.get("data")
                if not isinstance(root, dict) or not root:
                    return {"ok": False, "data": payload.get("data"), "errors": ["graphql_data_missing_or_invalid"]}

                top_key, top = next(iter(root.items()))
                if top is None:
                    return {"ok": False, "data": payload.get("data"), "errors": [f"graphql_top_level_null:{top_key}"]}
                if not isinstance(top, dict):
                    return {
                        "ok": False,
                        "data": payload.get("data"),
                        "errors": [f"graphql_top_level_not_object:{top_key}:{type(top).__name__}"],
                    }

                user_errors = top.get("userErrors")
                if user_errors:
                    return {"ok": False, "data": payload.get("data"), "errors": _extract_user_errors(user_errors)}
                return {"ok": True, "data": payload.get("data"), "errors": []}
            except Exception as e:
                err_msg = str(e).strip()
                if err_msg:
                    last_err = f"graphql_transport_error:{type(e).__name__}:{err_msg}"
                else:
                    last_err = f"graphql_transport_error:{type(e).__name__}"
                log.warning("Shopify GraphQL error attempt=%s/%s err=%s", attempt + 1, max_attempts, last_err)

            if allow_retries and attempt < (max_attempts - 1):
                time.sleep(0.25 * (attempt + 1))

        return {"ok": False, "data": None, "errors": [last_err or "unknown_error"]}

    def _http_post(self, url: str, headers: Dict[str, str], body: bytes) -> Tuple[int, str]:
        enforce_url_policy(url)
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
    raise NotImplementedError("shopify_writer._update_single_variant_fields is not implemented")