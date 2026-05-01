from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ops.autopilot_runtime_v1 import AutopilotRuntimeRequest, run_autopilot_runtime
from ops.autopilot_v2 import MIN_SPEND_FOR_SCALING
from ops.ops_orchestrator_v1 import OpsOrchestratorRequest, OpsOrchestratorV1
from synapse.infra.circuit_breaker import CircuitBreaker
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


def test_e2e_create_campaign_chain_dispatches_mock_publish(tmp_path: Path) -> None:
    vault = FakeVault(Decimal("50"))
    safe_client = _make_safe_client(tmp_path, live=False)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)

    runtime_result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-new",
            final_decision="approved",
            current_roas=0.9,
            spend=Decimal("0"),
            requested_budget=Decimal("10"),
            correlation_id="corr-e2e-create",
        ),
        vault=vault,
    )

    assert runtime_result.action == "test"
    assert runtime_result.publisher_action == "create_campaign"
    assert runtime_result.correlation_id == "corr-e2e-create"

    dispatch_result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime_result,
            campaign_payload={"name": "E2E Create Campaign", "budget_mxn": "10"},
            idempotency_key="e2e-create-001",
        )
    )

    assert dispatch_result.ok is True
    assert dispatch_result.status == "DISPATCHED"
    assert dispatch_result.publisher_action == "create_campaign"
    assert dispatch_result.correlation_id == "corr-e2e-create"
    assert dispatch_result.publish_result is not None
    assert dispatch_result.publish_result["ok"] is True
    assert dispatch_result.publish_result["mode"] == "mock"
    assert dispatch_result.publish_result["campaign_id"].startswith("MOCK_CAMP_")

    event_types = [e["event_type"] for e in _read_ledger_events(tmp_path)]
    assert "meta.create_campaign.attempt" in event_types
    assert "meta.create_campaign.result" in event_types


def test_e2e_pause_chain_dispatches_mock_autopause(tmp_path: Path) -> None:
    vault = FakeVault(Decimal("999"))
    safe_client = _make_safe_client(tmp_path, live=False)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)

    mid_roas = (0.7 + 1.0) / 2.0

    runtime_result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-gray",
            final_decision="approved",
            current_roas=mid_roas,
            spend=MIN_SPEND_FOR_SCALING,
            requested_budget=Decimal("15"),
            correlation_id="corr-e2e-pause",
        ),
        vault=vault,
    )

    assert runtime_result.action == "pause"
    assert runtime_result.reason == "pause_rule_triggered"
    assert runtime_result.publisher_action == "pause_campaign"
    assert runtime_result.correlation_id == "corr-e2e-pause"

    dispatch_result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime_result,
            campaign_id="camp-e2e-001",
            spend_today_mxn=Decimal("100"),
            cap_mxn=Decimal("100"),
        )
    )

    assert dispatch_result.ok is True
    assert dispatch_result.status == "DISPATCHED"
    assert dispatch_result.publisher_action == "pause_campaign"
    assert dispatch_result.correlation_id == "corr-e2e-pause"
    assert dispatch_result.publish_result is not None
    assert dispatch_result.publish_result["ok"] is True
    assert dispatch_result.publish_result["action"] == "PAUSE"
    assert dispatch_result.publish_result["campaign_id"] == "camp-e2e-001"

    event_types = [e["event_type"] for e in _read_ledger_events(tmp_path)]
    assert "meta.autopause.attempt" in event_types
    assert "meta.autopause.result" in event_types


def test_e2e_hold_chain_skips_publish(tmp_path: Path) -> None:
    vault = FakeVault(Decimal("999"))
    safe_client = _make_safe_client(tmp_path, live=False)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)

    runtime_result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-rejected",
            final_decision="rejected",
            current_roas=2.0,
            spend=Decimal("60"),
            requested_budget=Decimal("20"),
            correlation_id="corr-e2e-skip",
        ),
        vault=vault,
    )

    assert runtime_result.action == "hold"
    assert runtime_result.publisher_action is None
    assert runtime_result.correlation_id == "corr-e2e-skip"

    dispatch_result = orchestrator.dispatch(
        OpsOrchestratorRequest(runtime_result=runtime_result)
    )

    assert dispatch_result.ok is True
    assert dispatch_result.status == "SKIPPED"
    assert dispatch_result.publisher_action is None
    assert dispatch_result.correlation_id == "corr-e2e-skip"
    assert dispatch_result.publish_result is None

    assert _read_ledger_events(tmp_path) == []
