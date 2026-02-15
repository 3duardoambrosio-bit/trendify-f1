"""
Shopify Admin API Client (GraphQL, lectura).

ACERO, NO HUMO:
- stdlib-only (urllib), cero deps externas.
- Feature-flag gated: shopify_live_api=False → fixtures mock.
- Circuit breaker simple: tras N fallos consecutivos abre el circuito.
- Timeout 30s en todas las llamadas.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.feature_flags import FeatureFlags
from synapse.integrations.http_client import (
    HttpClientError,
    HttpTimeoutError,
    SimpleHttpClient,
)

# ── GraphQL queries ──────────────────────────────────────────────────

_PRODUCTS_QUERY = """
query GetProducts($first: Int!) {
  products(first: $first) {
    edges {
      node {
        id
        title
        handle
        status
        vendor
        productType
        createdAt
        updatedAt
        variants(first: 10) {
          edges {
            node {
              id
              title
              sku
              price
              inventoryQuantity
            }
          }
        }
      }
    }
  }
}
"""

_PRODUCT_QUERY = """
query GetProduct($id: ID!) {
  product(id: $id) {
    id
    title
    handle
    status
    vendor
    productType
    descriptionHtml
    createdAt
    updatedAt
    variants(first: 20) {
      edges {
        node {
          id
          title
          sku
          price
          inventoryQuantity
        }
      }
    }
  }
}
"""

_ORDERS_QUERY = """
query GetOrders($first: Int!) {
  orders(first: $first) {
    edges {
      node {
        id
        name
        displayFinancialStatus
        displayFulfillmentStatus
        createdAt
        totalPriceSet {
          shopMoney {
            amount
            currencyCode
          }
        }
        lineItems(first: 20) {
          edges {
            node {
              title
              quantity
              originalUnitPriceSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

_ORDER_QUERY = """
query GetOrder($id: ID!) {
  order(id: $id) {
    id
    name
    displayFinancialStatus
    displayFulfillmentStatus
    createdAt
    totalPriceSet {
      shopMoney {
        amount
        currencyCode
      }
    }
    lineItems(first: 20) {
      edges {
        node {
          title
          quantity
          originalUnitPriceSet {
            shopMoney {
              amount
              currencyCode
            }
          }
        }
      }
    }
  }
}
"""

# ── Circuit Breaker ──────────────────────────────────────────────────


@dataclass
class CircuitBreaker:
    """
    Circuit breaker simple: tras `threshold` fallos consecutivos,
    abre el circuito por `recovery_timeout_s` segundos.

    Estados: CLOSED (normal) → OPEN (rechaza) → HALF_OPEN (prueba 1).
    """

    threshold: int = 5
    recovery_timeout_s: float = 60.0

    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _state: str = field(default="CLOSED", init=False, repr=False)

    @property
    def state(self) -> str:
        if self._state == "OPEN":
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout_s:
                self._state = "HALF_OPEN"
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "CLOSED"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.threshold:
            self._state = "OPEN"

    def allow_request(self) -> bool:
        s = self.state
        if s == "CLOSED":
            return True
        if s == "HALF_OPEN":
            return True  # permite 1 intento de prueba
        return False


class CircuitOpenError(HttpClientError):
    """El circuit breaker está abierto; no se envían requests."""


# ── Fixtures loader ──────────────────────────────────────────────────

_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "shopify_admin"


def _load_fixture(name: str) -> Dict[str, Any]:
    path = _FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        return {"data": None, "error": f"fixture {name} not found"}
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# ── Client ───────────────────────────────────────────────────────────

_API_VERSION = "2024-10"
_TIMEOUT_S = 30.0


@dataclass
class ShopifyAdminClient:
    """
    Cliente de lectura para Shopify Admin GraphQL API.

    Si shopify_live_api=False en FeatureFlags, retorna datos mock
    desde fixtures/shopify_admin/.
    """

    shop: str = ""
    access_token: str = ""
    flags: FeatureFlags = field(default_factory=FeatureFlags)
    _http: SimpleHttpClient = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _breaker: CircuitBreaker = field(default_factory=CircuitBreaker, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.shop:
            self.shop = os.getenv("SYNAPSE_SHOPIFY_SHOP", "").strip()
        if not self.access_token:
            self.access_token = os.getenv("SYNAPSE_SHOPIFY_ACCESS_TOKEN", "").strip()
        self._http = SimpleHttpClient(
            retry_max=2,
            backoff_s=0.5,
            dry_run=False,
            user_agent="synapse-shopify-admin/1.0",
        )

    # ── Public API ───────────────────────────────────────────────

    def get_products(self, *, first: int = 50) -> Dict[str, Any]:
        if not self.flags.shopify_live_api:
            return _load_fixture("products")
        return self._graphql(_PRODUCTS_QUERY, {"first": first})

    def get_product(self, product_id: str) -> Dict[str, Any]:
        if not self.flags.shopify_live_api:
            # Intenta cargar fixture específica, fallback a genérica
            numeric = product_id.split("/")[-1] if "/" in product_id else product_id
            fixture = _load_fixture(f"product_{numeric}")
            if fixture.get("data") is not None:
                return fixture
            return _load_fixture("products")

        gid = product_id if product_id.startswith("gid://") else f"gid://shopify/Product/{product_id}"
        return self._graphql(_PRODUCT_QUERY, {"id": gid})

    def get_orders(self, *, first: int = 50) -> Dict[str, Any]:
        if not self.flags.shopify_live_api:
            return _load_fixture("orders")
        return self._graphql(_ORDERS_QUERY, {"first": first})

    def get_order(self, order_id: str) -> Dict[str, Any]:
        if not self.flags.shopify_live_api:
            numeric = order_id.split("/")[-1] if "/" in order_id else order_id
            fixture = _load_fixture(f"order_{numeric}")
            if fixture.get("data") is not None:
                return fixture
            return _load_fixture("orders")

        gid = order_id if order_id.startswith("gid://") else f"gid://shopify/Order/{order_id}"
        return self._graphql(_ORDER_QUERY, {"id": gid})

    # ── Internal ─────────────────────────────────────────────────

    def _endpoint(self) -> str:
        shop = self.shop.rstrip("/")
        if not shop.startswith("https://"):
            shop = f"https://{shop}"
        return f"{shop}/admin/api/{_API_VERSION}/graphql.json"

    def _graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.shop or not self.access_token:
            return {"data": None, "errors": [{"message": "Missing shop or access_token"}]}

        if not self._breaker.allow_request():
            raise CircuitOpenError(
                f"Circuit breaker OPEN for Shopify Admin API ({self.shop}). "
                f"Retrying in {self._breaker.recovery_timeout_s}s."
            )

        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            resp = self._http.post_json(
                url=self._endpoint(),
                payload=payload,
                headers={
                    "X-Shopify-Access-Token": self.access_token,
                    "Content-Type": "application/json",
                },
                timeout_s=_TIMEOUT_S,
            )
            data = resp.json()
            self._breaker.record_success()
            return data  # type: ignore[no-any-return]

        except HttpTimeoutError:
            self._breaker.record_failure()
            raise

        except HttpClientError:
            self._breaker.record_failure()
            raise
