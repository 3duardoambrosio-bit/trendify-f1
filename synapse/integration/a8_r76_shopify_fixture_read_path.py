from __future__ import annotations

import json
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from config.feature_flags import FeatureFlags
from infra.network_guard import enforce_url_policy
from synapse.integrations.shopify_admin_client import (
    ShopifyAdminClient,
    ShopifyReadOnlyViolation,
)

SHOPIFY_FIXTURE_PROBE_SHOP = "a8-r76-readonly-fixture-probe.myshopify.com"
SHOPIFY_GRAPHQL_ENDPOINT_PROBE = (
    "https://a8-r76-readonly-fixture-probe.myshopify.com/admin/api/2024-10/graphql.json"
)

MUTATION_PROBE = """
mutation {
  productCreate(input: {title: "A8-R76 forbidden mutation probe"}) {
    product {
      id
    }
  }
}
"""


class _NoHttpTransport:
    """Trap transport proving fixture-mode client did not reach HTTP."""

    def __init__(self) -> None:
        self.called = False
        self.calls: list[dict[str, Any]] = []

    def post_json(self, *, url: str, payload: Mapping[str, Any], headers: Mapping[str, str], timeout_s: float) -> Any:
        self.called = True
        self.calls.append(
            {
                "url": url,
                "payload_keys": sorted(payload.keys()),
                "header_keys": sorted(headers.keys()),
                "timeout_s": timeout_s,
            }
        )
        raise AssertionError("A8-R76 fixture read path must not call HTTP transport")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _local_read_only_flags() -> FeatureFlags:
    """Return FeatureFlags with all known live/write/spend toggles forced off."""
    flags = FeatureFlags.from_env() if hasattr(FeatureFlags, "from_env") else FeatureFlags()

    # Use concrete FeatureFlags dataclass field names, not read-only aliases.
    # `shopify_live_api` is a compatibility property backed by `shopify_live`;
    # forcing the alias name through dataclasses.replace() is a no-op.
    forced_false = {
        "shopify_live",
        "dropi_live",
        "meta_live",
        "spend_real_money",
    }

    updates: dict[str, bool] = {}

    if is_dataclass(flags):
        known = {field.name for field in fields(flags)}
        updates = {name: False for name in forced_false if name in known}
        if updates:
            return replace(flags, **updates)

    for name in forced_false:
        if hasattr(flags, name):
            setattr(flags, name, False)

    return flags


def _is_expected_shopify_policy_block(exc: RuntimeError) -> bool:
    message = str(exc)
    return "NETWORK_BLOCKED_BY_FLAGS" in message and "system=shopify" in message


def _network_guard_probe(url: str) -> Dict[str, Any]:
    try:
        enforce_url_policy(url)
    except RuntimeError as exc:
        expected = _is_expected_shopify_policy_block(exc)
        return {
            "url": url,
            "enforce_url_policy_called": True,
            "decision": "BLOCK" if expected else "ERROR",
            "expected_policy_block": expected,
            "policy_blocked": expected,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    except Exception as exc:  # pragma: no cover - defensive classification
        return {
            "url": url,
            "enforce_url_policy_called": True,
            "decision": "ERROR",
            "expected_policy_block": False,
            "policy_blocked": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    return {
        "url": url,
        "enforce_url_policy_called": True,
        "decision": "ALLOW",
        "expected_policy_block": False,
        "policy_blocked": False,
        "error_type": None,
        "error": None,
    }


def _edges_count(payload: Mapping[str, Any], collection: str) -> int:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return 0

    node = data.get(collection)
    if not isinstance(node, Mapping):
        return 0

    edges = node.get("edges")
    if not isinstance(edges, list):
        return 0

    return len(edges)


def _has_data_mapping(payload: Mapping[str, Any], key: str) -> bool:
    data = payload.get("data")
    return isinstance(data, Mapping) and isinstance(data.get(key), Mapping)


def build_shopify_fixture_read_path_payload() -> Dict[str, Any]:
    flags = _local_read_only_flags()
    client = ShopifyAdminClient(
        shop=SHOPIFY_FIXTURE_PROBE_SHOP,
        access_token="a8_r76_local_fixture_token",
        flags=flags,
    )

    endpoint = client._endpoint()
    network_guard = _network_guard_probe(endpoint)

    http_trap = _NoHttpTransport()
    client._http = http_trap  # type: ignore[assignment]

    products_payload = client.get_products(first=5)
    orders_payload = client.get_orders(first=5)
    product_payload = client.get_product("1001")
    order_payload = client.get_order("3001")

    mutation_rejected = False
    mutation_error_type = None
    mutation_error = None

    try:
        client._graphql(MUTATION_PROBE, {})
    except ShopifyReadOnlyViolation as exc:
        mutation_rejected = True
        mutation_error_type = type(exc).__name__
        mutation_error = str(exc)

    product_edges_count = _edges_count(products_payload, "products")
    order_edges_count = _edges_count(orders_payload, "orders")
    product_fixture_hit = _has_data_mapping(product_payload, "product")
    order_fixture_hit = _has_data_mapping(order_payload, "order")

    fixture_read_ok = (
        product_edges_count > 0
        and order_edges_count > 0
        and product_fixture_hit
        and order_fixture_hit
        and not http_trap.called
        and getattr(flags, "shopify_live_api", True) is False
    )

    network_guard_policy_blocked = (
        network_guard.get("decision") == "BLOCK"
        and network_guard.get("expected_policy_block") is True
    )

    status = (
        "OK"
        if fixture_read_ok and mutation_rejected and network_guard_policy_blocked
        else "BLOCKED"
    )

    return {
        "component": "shopify_read_only_fixture_read_path",
        "island": "A8-R76",
        "generated_at": _utc_now_iso(),
        "mode": "local_fixture_read_only",
        "status": status,
        "source_mode": "local_fixture_only",
        "external_io_attempted": False,
        "external_write_attempted": False,
        "live_shopify_attempted": False,
        "spend_attempted": False,
        "feature_flags": {
            "shopify_live_api": bool(getattr(flags, "shopify_live_api", False)),
            "dropi_live_orders": bool(getattr(flags, "dropi_live_orders", False)),
            "meta_live_ads": bool(getattr(flags, "meta_live_ads", False)),
            "spend_real_money": bool(getattr(flags, "spend_real_money", False)),
        },
        "network_guard": network_guard,
        "fixture_read": {
            "products_loaded": product_edges_count > 0,
            "orders_loaded": order_edges_count > 0,
            "product_fixture_hit": product_fixture_hit,
            "order_fixture_hit": order_fixture_hit,
            "product_edges_count": product_edges_count,
            "order_edges_count": order_edges_count,
            "http_transport_called": http_trap.called,
            "http_transport_call_count": len(http_trap.calls),
            "client_shop": SHOPIFY_FIXTURE_PROBE_SHOP,
            "endpoint_probe": endpoint,
        },
        "mutation_probe": {
            "operation_token": "mutation",
            "rejected_before_io": mutation_rejected,
            "error_type": mutation_error_type,
            "error": mutation_error,
        },
        "acceptance": {
            "read_fixtures_loaded": fixture_read_ok,
            "products_loaded": product_edges_count > 0,
            "orders_loaded": order_edges_count > 0,
            "no_http_transport": not http_trap.called,
            "no_external_io": True,
            "no_external_write": True,
            "network_guard_policy_blocked": network_guard_policy_blocked,
            "network_guard_decision": network_guard.get("decision"),
            "mutation_rejected_before_io": mutation_rejected,
            "evidence_visible_to_cockpit": status == "OK",
        },
    }


def run_shopify_fixture_read_path(out_dir: str | Path) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    payload = build_shopify_fixture_read_path_payload()

    summary_path = out / "shopify_fixture_read_path_summary.json"
    decision_path = out / "decision.json"
    ledger_path = out / "ledger.ndjson"

    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    decision = {
        "island": "A8-R76",
        "component": "shopify_read_only_fixture_read_path",
        "decision": payload["status"],
        "reason": "SHOPIFY_FIXTURE_READ_PATH_READY"
        if payload["status"] == "OK"
        else "SHOPIFY_FIXTURE_READ_PATH_BLOCKED",
        "summary_file": summary_path.name,
        "generated_at": payload["generated_at"],
    }

    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    ledger_event = {
        "ts": payload["generated_at"],
        "event": "shopify_read_only_fixture_read_path",
        "status": payload["status"],
        "summary_sha256_pending_external": False,
        "external_write_attempted": False,
        "live_shopify_attempted": False,
        "spend_attempted": False,
    }

    ledger_path.write_text(
        json.dumps(ledger_event, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "status": payload["status"],
        "out_dir": str(out),
        "summary_path": str(summary_path),
        "decision_path": str(decision_path),
        "ledger_path": str(ledger_path),
        "payload": payload,
    }


__all__ = [
    "build_shopify_fixture_read_path_payload",
    "run_shopify_fixture_read_path",
]
