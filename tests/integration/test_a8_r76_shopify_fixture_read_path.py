from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse.integration import a8_r76_shopify_fixture_read_path as r76
from synapse.integration.a8_r76_shopify_fixture_read_path import (
    build_shopify_fixture_read_path_payload,
    run_shopify_fixture_read_path,
)


def test_a8_r76_payload_reads_shopify_fixtures_without_http():
    payload = build_shopify_fixture_read_path_payload()

    assert payload["component"] == "shopify_read_only_fixture_read_path"
    assert payload["island"] == "A8-R76"
    assert payload["status"] == "OK"
    assert payload["source_mode"] == "local_fixture_only"

    assert payload["external_io_attempted"] is False
    assert payload["external_write_attempted"] is False
    assert payload["live_shopify_attempted"] is False
    assert payload["spend_attempted"] is False

    assert payload["feature_flags"]["shopify_live_api"] is False
    assert payload["fixture_read"]["products_loaded"] is True
    assert payload["fixture_read"]["orders_loaded"] is True
    assert payload["fixture_read"]["product_fixture_hit"] is True
    assert payload["fixture_read"]["order_fixture_hit"] is True
    assert payload["fixture_read"]["product_edges_count"] >= 1
    assert payload["fixture_read"]["order_edges_count"] >= 1
    assert payload["fixture_read"]["http_transport_called"] is False
    assert payload["fixture_read"]["http_transport_call_count"] == 0

    assert payload["network_guard"]["enforce_url_policy_called"] is True
    assert payload["network_guard"]["decision"] == "BLOCK"
    assert payload["network_guard"]["expected_policy_block"] is True
    assert payload["acceptance"]["network_guard_policy_blocked"] is True

    assert payload["mutation_probe"]["operation_token"] == "mutation"
    assert payload["mutation_probe"]["rejected_before_io"] is True
    assert payload["mutation_probe"]["error_type"] == "ShopifyReadOnlyViolation"

    assert payload["acceptance"]["read_fixtures_loaded"] is True
    assert payload["acceptance"]["no_http_transport"] is True
    assert payload["acceptance"]["evidence_visible_to_cockpit"] is True


def test_a8_r76_status_not_ok_when_network_guard_allows(monkeypatch):
    monkeypatch.setattr(r76, "enforce_url_policy", lambda url: None)

    payload = build_shopify_fixture_read_path_payload()

    assert payload["network_guard"]["decision"] == "ALLOW"
    assert payload["network_guard"]["expected_policy_block"] is False
    assert payload["status"] == "BLOCKED"
    assert payload["acceptance"]["network_guard_policy_blocked"] is False
    assert payload["acceptance"]["evidence_visible_to_cockpit"] is False


def test_a8_r76_status_not_ok_when_network_guard_raises_generic_error(monkeypatch):
    def raise_generic_error(url: str) -> None:
        raise ValueError("synthetic generic network guard error")

    monkeypatch.setattr(r76, "enforce_url_policy", raise_generic_error)

    payload = build_shopify_fixture_read_path_payload()

    assert payload["network_guard"]["decision"] == "ERROR"
    assert payload["network_guard"]["expected_policy_block"] is False
    assert payload["network_guard"]["error_type"] == "ValueError"
    assert payload["status"] == "BLOCKED"
    assert payload["acceptance"]["network_guard_policy_blocked"] is False


def test_a8_r76_status_ok_requires_expected_shopify_policy_block(monkeypatch):
    def raise_expected_policy_block(url: str) -> None:
        raise RuntimeError(
            "NETWORK_BLOCKED_BY_FLAGS: system=shopify url=https://example.myshopify.com/admin/api/graphql.json"
        )

    monkeypatch.setattr(r76, "enforce_url_policy", raise_expected_policy_block)

    payload = build_shopify_fixture_read_path_payload()

    assert payload["network_guard"]["decision"] == "BLOCK"
    assert payload["network_guard"]["expected_policy_block"] is True
    assert payload["status"] == "OK"
    assert payload["acceptance"]["network_guard_policy_blocked"] is True


def test_a8_r76_runner_writes_only_local_evidence(tmp_path: Path):
    result = run_shopify_fixture_read_path(tmp_path)

    assert result["status"] == "OK"

    summary = tmp_path / "shopify_fixture_read_path_summary.json"
    decision = tmp_path / "decision.json"
    ledger = tmp_path / "ledger.ndjson"

    assert summary.exists()
    assert decision.exists()
    assert ledger.exists()

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "OK"
    assert payload["acceptance"]["read_fixtures_loaded"] is True
    assert payload["fixture_read"]["http_transport_called"] is False

    decision_payload = json.loads(decision.read_text(encoding="utf-8"))
    assert decision_payload["component"] == "shopify_read_only_fixture_read_path"
    assert decision_payload["decision"] == "OK"

    events = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(events) == 1
    assert json.loads(events[0])["event"] == "shopify_read_only_fixture_read_path"


def test_a8_r76_module_has_no_direct_network_or_external_write_surface():
    source = Path("synapse/integration/a8_r76_shopify_fixture_read_path.py").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "urllib",
        "requests",
        "urlopen",
        "socket",
        "subprocess",
        "SimpleHttpClient(",
        ".post_json(",
        "shopify_writer",
    ]

    for token in forbidden:
        assert token not in source

    assert "ShopifyAdminClient" in source
    assert "enforce_url_policy" in source
    assert "shopify_live_api" in source
