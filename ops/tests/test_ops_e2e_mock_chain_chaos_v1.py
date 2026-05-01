from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ops.autopilot_runtime_v1 import (
    AutopilotRuntimeRequest,
    AutopilotRuntimeResult,
    run_autopilot_runtime,
)
from ops.autopilot_v2 import MIN_SPEND_FOR_SCALING
from ops.ops_orchestrator_v1 import OpsOrchestratorRequest, OpsOrchestratorV1
from synapse.infra.circuit_breaker import CircuitBreaker, CircuitOpenError
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.retry_policy import RetryPolicy
from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig


class FakeVault:
    def __init__(self, initial_budget: Decimal) -> None:
        self.remaining = Decimal(initial_budget)
        self.calls: list[tuple[Decimal, str]] = []

    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        amount = Decimal(amount)
        self.calls.append((amount, budget_type))
        if amount <= self.remaining:
            self.remaining -= amount
            return True
        return False


class ExplodingVault:
    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        raise RuntimeError("vault exploded")


def _make_safe_client(tmp_path: Path, *, live: bool = False) -> MetaSafeClient:
    flags = FeatureFlags(values={"meta_live_api": True}) if live else FeatureFlags(values={})
    return MetaSafeClient(
        feature_flags=flags,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
        idempotency_store=SimpleNamespace(path=tmp_path / "idem.sqlite3"),
        ledger=SimpleNamespace(path=tmp_path / "ledger.ndjson"),
        config=MetaSafeClientConfig(),
    )


def _read_ledger_events(tmp_path: Path) -> list[dict]:
    ledger_path = tmp_path / "ledger.ndjson"
    if not ledger_path.exists():
        return []
    lines = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _pause_runtime_result() -> AutopilotRuntimeResult:
    mid_roas = (0.7 + 1.0) / 2.0
    return run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-gray",
            final_decision="approved",
            current_roas=mid_roas,
            spend=MIN_SPEND_FOR_SCALING,
            requested_budget=Decimal("15"),
            correlation_id="corr-chaos-pause",
        ),
        vault=FakeVault(Decimal("999")),
    )


def test_chaos_vault_error_chain_skips_publish_and_writes_no_ledger(tmp_path: Path) -> None:
    safe_client = _make_safe_client(tmp_path, live=False)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)

    runtime_result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-vault-error",
            final_decision="approved",
            current_roas=1.1,
            spend=Decimal("20"),
            requested_budget=Decimal("15"),
            correlation_id="corr-chaos-vault",
        ),
        vault=ExplodingVault(),
    )

    assert runtime_result.action == "hold"
    assert runtime_result.reason == "vault_error_from_vault"
    assert runtime_result.publisher_action is None

    dispatch_result = orchestrator.dispatch(
        OpsOrchestratorRequest(runtime_result=runtime_result)
    )

    assert dispatch_result.ok is True
    assert dispatch_result.status == "SKIPPED"
    assert dispatch_result.publisher_action is None
    assert dispatch_result.publish_result is None
    assert _read_ledger_events(tmp_path) == []


def test_chaos_create_duplicate_dispatch_returns_cached_and_single_attempt(tmp_path: Path) -> None:
    safe_client = _make_safe_client(tmp_path, live=False)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)
    runtime_result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-new",
            final_decision="approved",
            current_roas=0.9,
            spend=Decimal("0"),
            requested_budget=Decimal("10"),
            correlation_id="corr-chaos-create",
        ),
        vault=FakeVault(Decimal("50")),
    )

    r1 = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime_result,
            campaign_payload={"name": "Chaos Create", "budget_mxn": "10"},
            idempotency_key="chaos-create-001",
        )
    )
    r2 = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime_result,
            campaign_payload={"name": "Chaos Create", "budget_mxn": "10"},
            idempotency_key="chaos-create-001",
        )
    )

    assert r1.ok is True
    assert r2.ok is True
    assert r1.status == "DISPATCHED"
    assert r2.status == "DISPATCHED"
    assert r1.publish_result is not None
    assert r2.publish_result is not None
    assert r1.publish_result["mode"] == "mock"
    assert r2.publish_result["mode"] == "cached"

    events = _read_ledger_events(tmp_path)
    attempt_events = [e for e in events if e["event_type"] == "meta.create_campaign.attempt"]
    assert len(attempt_events) == 1


def test_chaos_autopause_duplicate_dispatch_returns_cached_and_single_attempt(tmp_path: Path) -> None:
    safe_client = _make_safe_client(tmp_path, live=False)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)
    runtime_result = _pause_runtime_result()

    r1 = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime_result,
            campaign_id="camp-chaos-dup",
            spend_today_mxn=Decimal("100"),
            cap_mxn=Decimal("100"),
        )
    )
    r2 = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime_result,
            campaign_id="camp-chaos-dup",
            spend_today_mxn=Decimal("100"),
            cap_mxn=Decimal("100"),
        )
    )

    assert r1.ok is True
    assert r2.ok is True
    assert r1.status == "DISPATCHED"
    assert r2.status == "DISPATCHED"
    assert r1.publish_result is not None
    assert r2.publish_result is not None
    assert r1.publish_result["action"] == "PAUSE"
    assert r2.publish_result["mode"] == "cached"
    assert r2.publish_result["action"] == "PAUSE"

    events = _read_ledger_events(tmp_path)
    attempt_events = [e for e in events if e["event_type"] == "meta.autopause.attempt"]
    assert len(attempt_events) == 1


def test_chaos_pause_circuit_open_fails_closed_and_preserves_publish_error(tmp_path: Path) -> None:
    safe_client = _make_safe_client(tmp_path, live=True)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)
    runtime_result = _pause_runtime_result()

    with patch.object(safe_client.circuit_breaker, "call", side_effect=CircuitOpenError("breaker open")):
        result = orchestrator.dispatch(
            OpsOrchestratorRequest(
                runtime_result=runtime_result,
                campaign_id="camp-chaos-cb",
                spend_today_mxn=Decimal("100"),
                cap_mxn=Decimal("100"),
            )
        )

    assert result.ok is False
    assert result.status == "NOT_EXECUTED"
    assert result.error_code == "pause_not_executed"
    assert result.publish_result is not None
    assert result.publish_result["ok"] is False
    assert result.publish_result["error_code"] == "circuit_open"
    assert result.publish_result["correlation_id"] == "corr-chaos-pause"

    events = _read_ledger_events(tmp_path)
    event_types = [e["event_type"] for e in events]
    assert "meta.error" in event_types
