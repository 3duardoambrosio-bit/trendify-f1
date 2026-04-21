from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ops.autopilot_runtime_v1 import AutopilotRuntimeResult
from ops.ops_orchestrator_v1 import OpsOrchestratorRequest, OpsOrchestratorV1
from synapse.infra.circuit_breaker import CircuitBreaker
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.retry_policy import RetryPolicy
from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig


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


def _runtime_result(
    *,
    publisher_action,
    action: str,
    reason: str,
    correlation_id: str,
    spend: Decimal,
    requested_budget: Decimal,
    capital_reason,
) -> AutopilotRuntimeResult:
    return AutopilotRuntimeResult(
        product_id="prod-001",
        correlation_id=correlation_id,
        action=action,
        allocated_budget=requested_budget,
        reason=reason,
        final_decision="approved",
        current_roas=1.2,
        spend=spend,
        requested_budget=requested_budget,
        capital_reason=capital_reason,
        kill_action=None,
        publisher_action=publisher_action,
    )


def test_orchestrator_dispatches_create_campaign(tmp_path: Path) -> None:
    orchestrator = OpsOrchestratorV1(safe_client=_make_safe_client(tmp_path, live=False))
    runtime = _runtime_result(
        publisher_action="create_campaign",
        action="test",
        reason="test_within_budget",
        correlation_id="corr-orch-create",
        spend=Decimal("0"),
        requested_budget=Decimal("10"),
        capital_reason="approved",
    )

    result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime,
            campaign_payload={"name": "Bridge Campaign", "budget_mxn": "10"},
            idempotency_key="orch-create-001",
        )
    )

    assert result.ok is True
    assert result.status == "DISPATCHED"
    assert result.publisher_action == "create_campaign"
    assert result.correlation_id == "corr-orch-create"
    assert result.publish_result is not None
    assert result.publish_result["ok"] is True
    assert result.publish_result["mode"] == "mock"
    assert result.publish_result["campaign_id"].startswith("MOCK_CAMP_")


def test_orchestrator_dispatches_pause_campaign(tmp_path: Path) -> None:
    orchestrator = OpsOrchestratorV1(safe_client=_make_safe_client(tmp_path, live=False))
    runtime = _runtime_result(
        publisher_action="pause_campaign",
        action="pause",
        reason="pause_rule_triggered",
        correlation_id="corr-orch-pause",
        spend=Decimal("90"),
        requested_budget=Decimal("0"),
        capital_reason=None,
    )

    result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime,
            campaign_id="camp-bridge-001",
            spend_today_mxn=Decimal("90"),
            cap_mxn=Decimal("100"),
        )
    )

    assert result.ok is True
    assert result.status == "DISPATCHED"
    assert result.publisher_action == "pause_campaign"
    assert result.correlation_id == "corr-orch-pause"
    assert result.publish_result is not None
    assert result.publish_result["ok"] is True
    assert result.publish_result["action"] == "PAUSE"


def test_orchestrator_skips_when_no_publisher_action(tmp_path: Path) -> None:
    orchestrator = OpsOrchestratorV1(safe_client=_make_safe_client(tmp_path, live=False))
    runtime = _runtime_result(
        publisher_action=None,
        action="hold",
        reason="not_approved_by_buyer",
        correlation_id="corr-orch-skip",
        spend=Decimal("10"),
        requested_budget=Decimal("0"),
        capital_reason=None,
    )

    result = orchestrator.dispatch(OpsOrchestratorRequest(runtime_result=runtime))

    assert result.ok is True
    assert result.status == "SKIPPED"
    assert result.publisher_action is None
    assert result.error_code is None
    assert result.publish_result is None


def test_orchestrator_fails_closed_when_pause_not_executed(tmp_path: Path) -> None:
    orchestrator = OpsOrchestratorV1(safe_client=_make_safe_client(tmp_path, live=False))
    runtime = _runtime_result(
        publisher_action="pause_campaign",
        action="pause",
        reason="pause_rule_triggered",
        correlation_id="corr-orch-pause-noexec",
        spend=Decimal("10"),
        requested_budget=Decimal("0"),
        capital_reason=None,
    )

    result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=runtime,
            campaign_id="camp-bridge-002",
            spend_today_mxn=Decimal("10"),
            cap_mxn=Decimal("100"),
        )
    )

    assert result.ok is False
    assert result.status == "NOT_EXECUTED"
    assert result.error_code == "pause_not_executed"
    assert result.publish_result is not None
    assert result.publish_result["ok"] is True
    assert result.publish_result["action"] == "NONE"
