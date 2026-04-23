from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


class ExplodingVault:
    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        raise RuntimeError("vault exploded")


@dataclass(frozen=True)
class BurnInSummary:
    cycles: int
    scenario_count_per_cycle: int
    dispatch_count: int
    ledger_event_count: int
    status_counts: dict[str, int]
    action_counts: dict[str, int]
    publisher_action_counts: dict[str, int]
    output_dir: str
    ledger_path: str
    idempotency_db_path: str
    summary_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _make_safe_client(output_dir: Path) -> MetaSafeClient:
    return MetaSafeClient(
        feature_flags=FeatureFlags(values={}),
        retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
        idempotency_store=SimpleNamespace(path=output_dir / "idem.sqlite3"),
        ledger=SimpleNamespace(path=output_dir / "ledger.ndjson"),
        config=MetaSafeClientConfig(),
    )


def _read_ledger_events(ledger_path: Path) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    lines = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def run_burnin_mock(*, cycles: int, output_dir: Path | str) -> BurnInSummary:
    if cycles <= 0:
        raise ValueError("cycles_must_be_positive")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    safe_client = _make_safe_client(out)
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)

    status_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    publisher_action_counts: Counter[str] = Counter()
    dispatch_count = 0

    mid_roas = (0.7 + 1.0) / 2.0

    for cycle in range(1, cycles + 1):
        create_runtime = run_autopilot_runtime(
            AutopilotRuntimeRequest(
                product_id=f"burnin-create-{cycle}",
                final_decision="approved",
                current_roas=0.9,
                spend=Decimal("0"),
                requested_budget=Decimal("10"),
                correlation_id=f"burnin-create-{cycle}",
            ),
            vault=FakeVault(Decimal("100")),
        )
        create_dispatch = orchestrator.dispatch(
            OpsOrchestratorRequest(
                runtime_result=create_runtime,
                campaign_payload={"name": f"BurnIn Create {cycle}", "budget_mxn": "10"},
                idempotency_key=f"burnin-create-idem-{cycle}",
            )
        )
        dispatch_count += 1
        status_counts[create_dispatch.status] += 1
        action_counts[create_runtime.action] += 1
        publisher_action_counts[str(create_runtime.publisher_action)] += 1

        pause_runtime = run_autopilot_runtime(
            AutopilotRuntimeRequest(
                product_id=f"burnin-pause-{cycle}",
                final_decision="approved",
                current_roas=mid_roas,
                spend=MIN_SPEND_FOR_SCALING,
                requested_budget=Decimal("15"),
                correlation_id=f"burnin-pause-{cycle}",
            ),
            vault=FakeVault(Decimal("999")),
        )
        pause_dispatch = orchestrator.dispatch(
            OpsOrchestratorRequest(
                runtime_result=pause_runtime,
                campaign_id=f"camp-burnin-{cycle}",
                spend_today_mxn=Decimal("100"),
                cap_mxn=Decimal("100"),
            )
        )
        dispatch_count += 1
        status_counts[pause_dispatch.status] += 1
        action_counts[pause_runtime.action] += 1
        publisher_action_counts[str(pause_runtime.publisher_action)] += 1

        hold_runtime = run_autopilot_runtime(
            AutopilotRuntimeRequest(
                product_id=f"burnin-hold-{cycle}",
                final_decision="rejected",
                current_roas=2.0,
                spend=Decimal("60"),
                requested_budget=Decimal("20"),
                correlation_id=f"burnin-hold-{cycle}",
            ),
            vault=FakeVault(Decimal("999")),
        )
        hold_dispatch = orchestrator.dispatch(
            OpsOrchestratorRequest(runtime_result=hold_runtime)
        )
        dispatch_count += 1
        status_counts[hold_dispatch.status] += 1
        action_counts[hold_runtime.action] += 1
        publisher_action_counts[str(hold_runtime.publisher_action)] += 1

        vault_error_runtime = run_autopilot_runtime(
            AutopilotRuntimeRequest(
                product_id=f"burnin-vault-error-{cycle}",
                final_decision="approved",
                current_roas=1.1,
                spend=Decimal("20"),
                requested_budget=Decimal("15"),
                correlation_id=f"burnin-vault-error-{cycle}",
            ),
            vault=ExplodingVault(),
        )
        vault_error_dispatch = orchestrator.dispatch(
            OpsOrchestratorRequest(runtime_result=vault_error_runtime)
        )
        dispatch_count += 1
        status_counts[vault_error_dispatch.status] += 1
        action_counts[vault_error_runtime.action] += 1
        publisher_action_counts[str(vault_error_runtime.publisher_action)] += 1

    ledger_path = out / "ledger.ndjson"
    summary_path = out / "burnin_summary.json"
    idem_path = out / "idem.sqlite3"

    ledger_events = _read_ledger_events(ledger_path)

    summary = BurnInSummary(
        cycles=cycles,
        scenario_count_per_cycle=4,
        dispatch_count=dispatch_count,
        ledger_event_count=len(ledger_events),
        status_counts=dict(status_counts),
        action_counts=dict(action_counts),
        publisher_action_counts=dict(publisher_action_counts),
        output_dir=str(out),
        ledger_path=str(ledger_path),
        idempotency_db_path=str(idem_path),
        summary_path=str(summary_path),
    )

    summary_path.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return summary
