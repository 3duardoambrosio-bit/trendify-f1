from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from infra.network_guard import enforce_url_policy
from synapse.integrations.shopify_admin_client import (
    ShopifyReadOnlyViolation,
    _assert_read_only_graphql_query,
    _graphql_operation_token,
)

READ_QUERY = """
query A8R75ReadOnlyDryRun {
  shop {
    name
  }
}
"""

MUTATION_PROBE = """
mutation A8R75MutationProbe {
  productCreate(input: {title: "A8-R75 forbidden mutation probe"}) {
    product {
      id
    }
  }
}
"""

SHOPIFY_GRAPHQL_ENDPOINT_PROBE = (
    "https://a8-r75-readonly-probe.myshopify.com/admin/api/2024-10/graphql.json"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_expected_shopify_policy_block(exc: RuntimeError) -> bool:
    message = str(exc)
    return (
        "NETWORK_BLOCKED_BY_FLAGS" in message
        and "system=shopify" in message
    )


def _network_guard_probe(url: str) -> Dict[str, Any]:
    try:
        enforce_url_policy(url)
    except RuntimeError as exc:
        is_expected_policy_block = _is_expected_shopify_policy_block(exc)
        return {
            "url": url,
            "enforce_url_policy_called": True,
            "decision": "BLOCK" if is_expected_policy_block else "ERROR",
            "expected_policy_block": is_expected_policy_block,
            "policy_blocked": is_expected_policy_block,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    except Exception as exc:
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


def build_shopify_read_only_dry_run_payload() -> Dict[str, Any]:
    read_token = _graphql_operation_token(READ_QUERY)
    _assert_read_only_graphql_query(READ_QUERY)

    mutation_rejected = False
    mutation_error = None
    mutation_error_type = None

    try:
        _assert_read_only_graphql_query(MUTATION_PROBE)
    except ShopifyReadOnlyViolation as exc:
        mutation_rejected = True
        mutation_error = str(exc)
        mutation_error_type = type(exc).__name__

    network_guard = _network_guard_probe(SHOPIFY_GRAPHQL_ENDPOINT_PROBE)

    network_guard_policy_blocked = (
        network_guard.get("decision") == "BLOCK"
        and network_guard.get("expected_policy_block") is True
    )

    status = (
        "OK"
        if read_token == "query" and mutation_rejected and network_guard_policy_blocked
        else "BLOCKED"
    )

    return {
        "island": "A8-R75",
        "component": "shopify_read_only_dry_run",
        "status": status,
        "generated_at": _utc_now_iso(),
        "mode": "local_dry_run",
        "external_io_attempted": False,
        "external_write_attempted": False,
        "live_shopify_attempted": False,
        "spend_attempted": False,
        "read_query": {
            "operation_token": read_token,
            "accepted_by_read_only_guard": read_token == "query",
        },
        "mutation_probe": {
            "operation_token": _graphql_operation_token(MUTATION_PROBE),
            "rejected_before_io": mutation_rejected,
            "error_type": mutation_error_type,
            "error": mutation_error,
        },
        "network_guard": network_guard,
        "acceptance": {
            "read_query_allowed": read_token == "query",
            "mutation_rejected_before_io": mutation_rejected,
            "no_external_io": True,
            "no_external_write": True,
            "network_guard_policy_blocked": network_guard_policy_blocked,
            "network_guard_decision": network_guard.get("decision"),
            "evidence_visible_to_cockpit": status == "OK",
        },
    }


def run_shopify_read_only_dry_run(out_dir: str | Path) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    payload = build_shopify_read_only_dry_run_payload()

    summary_path = out / "shopify_read_only_dry_run_summary.json"
    decision_path = out / "decision.json"
    ledger_path = out / "ledger.ndjson"

    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    decision = {
        "island": "A8-R75",
        "decision": payload["status"],
        "component": payload["component"],
        "generated_at": payload["generated_at"],
        "reason_codes": [
            "SHOPIFY_READ_ONLY_DRY_RUN",
            "GRAPHQL_MUTATION_REJECTED_BEFORE_IO",
            "NO_EXTERNAL_WRITE",
            "NETWORK_GUARD_PROBED",
        ],
        "summary_file": summary_path.name,
    }

    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    ledger_event = {
        "ts": payload["generated_at"],
        "island": "A8-R75",
        "event": "shopify_read_only_dry_run",
        "status": payload["status"],
        "external_io_attempted": False,
        "external_write_attempted": False,
        "mutation_rejected_before_io": payload["mutation_probe"]["rejected_before_io"],
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
    "READ_QUERY",
    "MUTATION_PROBE",
    "SHOPIFY_GRAPHQL_ENDPOINT_PROBE",
    "build_shopify_read_only_dry_run_payload",
    "run_shopify_read_only_dry_run",
]
