from __future__ import annotations

import json
from pathlib import Path

import synapse.integration.a8_r75_shopify_readonly_dryrun as r75
from synapse.integration.a8_r75_shopify_readonly_dryrun import (
    MUTATION_PROBE,
    READ_QUERY,
    build_shopify_read_only_dry_run_payload,
    run_shopify_read_only_dry_run,
)


def test_a8_r75_payload_is_read_only_and_rejects_mutation_before_io():
    payload = build_shopify_read_only_dry_run_payload()

    assert payload["component"] == "shopify_read_only_dry_run"
    assert payload["status"] == "OK"
    assert payload["external_io_attempted"] is False
    assert payload["external_write_attempted"] is False
    assert payload["live_shopify_attempted"] is False
    assert payload["spend_attempted"] is False

    assert payload["read_query"]["operation_token"] == "query"
    assert payload["read_query"]["accepted_by_read_only_guard"] is True
    assert payload["mutation_probe"]["operation_token"] == "mutation"
    assert payload["mutation_probe"]["rejected_before_io"] is True
    assert payload["mutation_probe"]["error_type"] == "ShopifyReadOnlyViolation"

    assert payload["network_guard"]["enforce_url_policy_called"] is True
    assert payload["network_guard"]["decision"] == "BLOCK"
    assert payload["network_guard"]["expected_policy_block"] is True
    assert payload["acceptance"]["network_guard_policy_blocked"] is True
    assert payload["acceptance"]["network_guard_decision"] == "BLOCK"


def test_a8_r75_status_not_ok_when_network_guard_allows(monkeypatch):
    monkeypatch.setattr(r75, "enforce_url_policy", lambda url: None)

    payload = build_shopify_read_only_dry_run_payload()

    assert payload["network_guard"]["decision"] == "ALLOW"
    assert payload["network_guard"]["expected_policy_block"] is False
    assert payload["status"] == "BLOCKED"
    assert payload["acceptance"]["network_guard_policy_blocked"] is False
    assert payload["acceptance"]["evidence_visible_to_cockpit"] is False


def test_a8_r75_status_not_ok_when_network_guard_raises_generic_error(monkeypatch):
    def raise_generic_error(url: str) -> None:
        raise ValueError("synthetic generic network guard error")

    monkeypatch.setattr(r75, "enforce_url_policy", raise_generic_error)

    payload = build_shopify_read_only_dry_run_payload()

    assert payload["network_guard"]["decision"] == "ERROR"
    assert payload["network_guard"]["expected_policy_block"] is False
    assert payload["network_guard"]["error_type"] == "ValueError"
    assert payload["status"] == "BLOCKED"
    assert payload["acceptance"]["network_guard_policy_blocked"] is False


def test_a8_r75_status_ok_requires_expected_shopify_policy_block(monkeypatch):
    def raise_expected_policy_block(url: str) -> None:
        raise RuntimeError(
            "NETWORK_BLOCKED_BY_FLAGS: system=shopify url=https://example.myshopify.com/admin/api/graphql.json"
        )

    monkeypatch.setattr(r75, "enforce_url_policy", raise_expected_policy_block)

    payload = build_shopify_read_only_dry_run_payload()

    assert payload["network_guard"]["decision"] == "BLOCK"
    assert payload["network_guard"]["expected_policy_block"] is True
    assert payload["status"] == "OK"
    assert payload["acceptance"]["network_guard_policy_blocked"] is True


def test_a8_r75_runner_writes_only_local_evidence(tmp_path: Path):
    result = run_shopify_read_only_dry_run(tmp_path)

    assert result["status"] == "OK"

    summary = tmp_path / "shopify_read_only_dry_run_summary.json"
    decision = tmp_path / "decision.json"
    ledger = tmp_path / "ledger.ndjson"

    assert summary.exists()
    assert decision.exists()
    assert ledger.exists()

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["acceptance"]["mutation_rejected_before_io"] is True
    assert payload["acceptance"]["network_guard_policy_blocked"] is True
    assert payload["acceptance"]["no_external_io"] is True
    assert payload["acceptance"]["no_external_write"] is True


def test_a8_r75_module_has_no_direct_network_or_write_surface():
    source = Path("synapse/integration/a8_r75_shopify_readonly_dryrun.py").read_text(
        encoding="utf-8"
    )

    forbidden = (
        "requests.",
        "httpx.",
        "urllib.request.urlopen",
        "socket.",
    )

    for token in forbidden:
        assert token not in source

    assert "enforce_url_policy" in source
    assert "mutation" in MUTATION_PROBE
    assert "query" in READ_QUERY
