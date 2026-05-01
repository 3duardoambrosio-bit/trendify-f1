"""
Tests para ShopifyAdminClient — mock + live contract.
No se hacen llamadas reales a Shopify.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from config.feature_flags import FeatureFlags
from synapse.integrations.http_client import HttpClientError, HttpTimeoutError
from synapse.integrations.shopify_admin_client import (
    CircuitBreaker,
    CircuitOpenError,
    ShopifyAdminClient,
    _load_fixture,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mock_flags(*, shopify_live: bool = False) -> FeatureFlags:
    """Feature flags con shopify_live_api configurable."""
    return FeatureFlags(
        meta_live_api=False,
        shopify_live_api=shopify_live,
        dropi_live_orders=False,
        spend_real_money=False,
    )


def _client(*, live: bool = False) -> ShopifyAdminClient:
    return ShopifyAdminClient(
        shop="test-shop.myshopify.com",
        access_token="shpat_fake_token",
        flags=_mock_flags(shopify_live=live),
    )


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


# ──────────────────────────────────────────────────────────────────────────────
# Fixture loading
# ──────────────────────────────────────────────────────────────────────────────

class TestFixtureLoading:
    def test_load_products_fixture(self):
        data = _load_fixture("products")
        assert "data" in data
        assert data["data"]["products"]["edges"]

    def test_load_orders_fixture(self):
        data = _load_fixture("orders")
        assert "data" in data
        assert data["data"]["orders"]["edges"]

    def test_load_product_by_id(self):
        data = _load_fixture("product_1001")
        assert data["data"]["product"]["id"] == "gid://shopify/Product/1001"

    def test_load_order_by_id(self):
        data = _load_fixture("order_3001")
        assert data["data"]["order"]["id"] == "gid://shopify/Order/3001"

    def test_missing_fixture_returns_error(self):
        data = _load_fixture("nonexistent_thing")
        assert data["data"] is None
        assert "not found" in data["error"]


# ──────────────────────────────────────────────────────────────────────────────
# Mock mode (shopify_live_api=False)
# ──────────────────────────────────────────────────────────────────────────────

class TestMockMode:
    def test_get_products_returns_fixture(self):
        client = _client(live=False)
        result = client.get_products()
        products = result["data"]["products"]["edges"]
        assert len(products) >= 1
        assert products[0]["node"]["title"]

    def test_get_product_by_id(self):
        client = _client(live=False)
        result = client.get_product("1001")
        product = result["data"]["product"]
        assert product["id"] == "gid://shopify/Product/1001"
        assert product["title"] == "Camiseta Básica Negra"

    def test_get_product_by_gid(self):
        client = _client(live=False)
        result = client.get_product("gid://shopify/Product/1001")
        assert result["data"]["product"]["id"] == "gid://shopify/Product/1001"

    def test_get_product_unknown_falls_back(self):
        client = _client(live=False)
        result = client.get_product("9999")
        assert result["data"] is not None

    def test_get_orders_returns_fixture(self):
        client = _client(live=False)
        result = client.get_orders()
        orders = result["data"]["orders"]["edges"]
        assert len(orders) >= 1
        assert orders[0]["node"]["name"]

    def test_get_order_by_id(self):
        client = _client(live=False)
        result = client.get_order("3001")
        order = result["data"]["order"]
        assert order["id"] == "gid://shopify/Order/3001"
        assert order["name"] == "#1001"

    def test_get_order_by_gid(self):
        client = _client(live=False)
        result = client.get_order("gid://shopify/Order/3001")
        assert result["data"]["order"]["name"] == "#1001"

    def test_mock_mode_never_calls_http(self):
        client = _client(live=False)
        with patch.object(client._http, "post_json") as mock_post:
            client.get_products()
            client.get_product("1001")
            client.get_orders()
            client.get_order("3001")
            mock_post.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# Product data structure
# ──────────────────────────────────────────────────────────────────────────────

class TestProductStructure:
    def test_product_has_variants(self):
        client = _client(live=False)
        result = client.get_product("1001")
        variants = result["data"]["product"]["variants"]["edges"]
        assert len(variants) >= 1
        node = variants[0]["node"]
        assert "sku" in node
        assert "price" in node
        assert "inventoryQuantity" in node

    def test_products_list_has_required_fields(self):
        client = _client(live=False)
        result = client.get_products()
        node = result["data"]["products"]["edges"][0]["node"]
        for key in ("id", "title", "handle", "status", "vendor"):
            assert key in node, f"Missing key: {key}"


# ──────────────────────────────────────────────────────────────────────────────
# Order data structure
# ──────────────────────────────────────────────────────────────────────────────

class TestOrderStructure:
    def test_order_has_line_items(self):
        client = _client(live=False)
        result = client.get_order("3001")
        items = result["data"]["order"]["lineItems"]["edges"]
        assert len(items) >= 1
        node = items[0]["node"]
        assert "title" in node
        assert "quantity" in node

    def test_order_has_total_price(self):
        client = _client(live=False)
        result = client.get_order("3001")
        total = result["data"]["order"]["totalPriceSet"]["shopMoney"]
        assert total["amount"] == "598.00"
        assert total["currencyCode"] == "MXN"


# ──────────────────────────────────────────────────────────────────────────────
# Circuit Breaker
# ──────────────────────────────────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(threshold=3)
        assert cb.state == "CLOSED"
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(threshold=3, recovery_timeout_s=60.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.allow_request() is False

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "CLOSED"
        assert cb.allow_request() is True

    def test_success_resets_count(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state == "CLOSED"

    def test_transitions_to_half_open(self):
        cb = CircuitBreaker(threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        assert cb.state == "OPEN"
        time.sleep(0.02)
        assert cb.state == "HALF_OPEN"
        assert cb.allow_request() is True

    def test_half_open_allows_exactly_one_probe_request(self):
        cb = CircuitBreaker(threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == "HALF_OPEN"
        assert cb.allow_request() is True
        assert cb.allow_request() is False

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == "HALF_OPEN"
        cb.record_success()
        assert cb.state == "CLOSED"

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == "HALF_OPEN"
        cb.record_failure()
        assert cb.state == "OPEN"

    def test_half_open_failed_probe_reopens_and_blocks(self):
        cb = CircuitBreaker(threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == "HALF_OPEN"
        assert cb.allow_request() is True
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.allow_request() is False


# ──────────────────────────────────────────────────────────────────────────────
# Client configuration
# ──────────────────────────────────────────────────────────────────────────────

class TestClientConfig:
    def test_endpoint_url_format(self):
        client = _client()
        url = client._endpoint()
        assert url == "https://test-shop.myshopify.com/admin/api/2024-10/graphql.json"

    def test_endpoint_strips_trailing_slash(self):
        client = ShopifyAdminClient(
            shop="test-shop.myshopify.com/",
            access_token="tok",
            flags=_mock_flags(),
        )
        assert client._endpoint().count("//") == 1

    def test_endpoint_adds_https(self):
        client = ShopifyAdminClient(
            shop="my.shop.com",
            access_token="tok",
            flags=_mock_flags(),
        )
        assert client._endpoint().startswith("https://")

    def test_missing_credentials_returns_error(self):
        client = ShopifyAdminClient(
            shop="",
            access_token="",
            flags=_mock_flags(shopify_live=True),
        )
        result = client.get_products()
        assert result["data"] is None
        assert result["errors"][0]["message"] == "Missing shop or access_token"

    def test_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_SHOPIFY_SHOP", "env-shop.myshopify.com")
        monkeypatch.setenv("SYNAPSE_SHOPIFY_ACCESS_TOKEN", "shpat_env_token")
        client = ShopifyAdminClient(flags=_mock_flags())
        assert client.shop == "env-shop.myshopify.com"
        assert client.access_token == "shpat_env_token"


# ──────────────────────────────────────────────────────────────────────────────
# Live mode circuit breaker integration
# ──────────────────────────────────────────────────────────────────────────────

class TestLiveModeCircuitBreaker:
    def test_circuit_open_raises(self):
        client = _client(live=True)
        for _ in range(5):
            client._breaker.record_failure()
        with pytest.raises(CircuitOpenError, match="Circuit breaker OPEN"):
            client.get_products()

    def test_graphql_missing_creds_no_http_call(self):
        client = ShopifyAdminClient(
            shop="",
            access_token="",
            flags=_mock_flags(shopify_live=True),
        )
        with patch.object(client._http, "post_json") as mock_post:
            result = client.get_orders()
            mock_post.assert_not_called()
            assert result["data"] is None
            assert result["errors"][0]["message"] == "Missing shop or access_token"

    def test_live_success_returns_json_and_resets_breaker(self):
        client = _client(live=True)
        client._breaker.record_failure()
        client._breaker.record_failure()
        assert client._breaker.state == "CLOSED"

        fake_payload = {"data": {"products": {"edges": []}}}
        with patch.object(client._http, "post_json", return_value=_FakeResponse(fake_payload)) as mock_post:
            result = client.get_products(first=7)

        assert result == fake_payload
        assert client._breaker.state == "CLOSED"
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        assert kwargs["url"] == "https://test-shop.myshopify.com/admin/api/2024-10/graphql.json"
        assert kwargs["headers"]["X-Shopify-Access-Token"] == "shpat_fake_token"
        assert kwargs["timeout_s"] == 30.0
        assert kwargs["payload"]["variables"] == {"first": 7}

    def test_live_timeout_records_failure_and_raises(self):
        client = _client(live=True)

        with patch.object(client._http, "post_json", side_effect=HttpTimeoutError("timeout")):
            with pytest.raises(HttpTimeoutError, match="timeout"):
                client.get_orders(first=3)

        assert client._breaker.state == "CLOSED"
        assert client._breaker._failure_count == 1

    def test_live_http_client_error_records_failure_and_raises(self):
        client = _client(live=True)

        with patch.object(client._http, "post_json", side_effect=HttpClientError("boom")):
            with pytest.raises(HttpClientError, match="boom"):
                client.get_products(first=2)

        assert client._breaker.state == "CLOSED"
        assert client._breaker._failure_count == 1

    def test_live_repeated_http_failures_open_breaker(self):
        client = _client(live=True)

        with patch.object(client._http, "post_json", side_effect=HttpClientError("boom")):
            for _ in range(5):
                with pytest.raises(HttpClientError):
                    client.get_products()

        assert client._breaker.state == "OPEN"
        with pytest.raises(CircuitOpenError, match="Circuit breaker OPEN"):
            client.get_products()

    def test_half_open_success_from_live_path_closes_breaker(self):
        client = _client(live=True)
        client._breaker.threshold = 1
        client._breaker.recovery_timeout_s = 0.01

        with patch.object(client._http, "post_json", side_effect=HttpClientError("boom")):
            with pytest.raises(HttpClientError):
                client.get_products()

        assert client._breaker.state == "OPEN"
        time.sleep(0.02)
        assert client._breaker.state == "HALF_OPEN"

        fake_payload = {"data": {"products": {"edges": []}}}
        with patch.object(client._http, "post_json", return_value=_FakeResponse(fake_payload)):
            result = client.get_products()

        assert result == fake_payload
        assert client._breaker.state == "CLOSED"

    def test_half_open_failed_probe_blocks_following_live_request(self):
        client = _client(live=True)
        client._breaker.threshold = 1
        client._breaker.recovery_timeout_s = 0.01

        with patch.object(client._http, "post_json", side_effect=HttpClientError("boom")):
            with pytest.raises(HttpClientError):
                client.get_products()

        assert client._breaker.state == "OPEN"
        time.sleep(0.02)
        assert client._breaker.state == "HALF_OPEN"

        with patch.object(client._http, "post_json", side_effect=HttpClientError("boom")) as mock_post:
            with pytest.raises(HttpClientError, match="boom"):
                client.get_products()
            assert mock_post.call_count == 1

        assert client._breaker.state == "OPEN"

        with patch.object(client._http, "post_json") as mock_post_blocked:
            with pytest.raises(CircuitOpenError, match="Circuit breaker OPEN"):
                client.get_products()
            mock_post_blocked.assert_not_called()