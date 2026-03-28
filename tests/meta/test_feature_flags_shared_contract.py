from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config.feature_flags import FeatureFlags as ConfigFeatureFlags
from infra.feature_flags import FeatureFlags as InfraFeatureFlags
from infra.vault import VaultSnapshot
from synapse.core.orchestrator import decide
from synapse.infra.feature_flags import FeatureFlags as SynapseFeatureFlags
from synapse.infra.circuit_breaker import CircuitBreaker
from synapse.infra.idempotency_store import IdempotencyStore
from synapse.infra.ledger_f1_core import Ledger
from synapse.infra.retry_policy import RetryPolicy
from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig


def _vault(
    total: str = "300",
    learning: str = "150",
    operational: str = "100",
    reserve: str = "50",
    spent_learning: str = "0",
    spent_operational: str = "0",
) -> VaultSnapshot:
    return VaultSnapshot(
        total_budget=Decimal(total),
        learning_budget=Decimal(learning),
        operational_budget=Decimal(operational),
        reserve_budget=Decimal(reserve),
        spent_learning=Decimal(spent_learning),
        spent_operational=Decimal(spent_operational),
    )


def _product(pid: str = "P2", score: float = 0.9, margin: float = 55.0) -> SimpleNamespace:
    return SimpleNamespace(
        product_id=pid,
        match_score=score,
        margin_percent=margin,
    )


def _write_ops_tick(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_feature_flags_import_surfaces_share_single_class() -> None:
    assert ConfigFeatureFlags is InfraFeatureFlags
    assert ConfigFeatureFlags is SynapseFeatureFlags


def test_shared_flags_instance_supports_orchestrator_and_safe_client(tmp_path: Path) -> None:
    shared_flags = ConfigFeatureFlags(
        spend_real_money=False,
        values={"meta_live_api": True},
    )

    assert shared_flags.meta_live is True
    assert shared_flags.meta_live_api is True
    assert shared_flags.is_on("meta_live_api", default=False) is True
    assert shared_flags.spend_real_money is False

    ops = tmp_path / "ops.json"
    _write_ops_tick(
        ops,
        {
            "checks": {
                "reconcile_preflight": {"blocked": False, "status": "ok"},
            },
            "steps": [],
        },
    )

    decisions = decide(
        _vault(),
        [_product("P2", 0.9)],
        [],
        [],
        feature_flags=shared_flags,
        ops_tick_path=str(ops),
        decisions_dir=str(tmp_path / "decisions"),
    )

    launch = [d for d in decisions if d.action_type == "launch_test"][0]
    assert "spend_real_money_disabled" in launch.blocking_conditions

    with patch("synapse.meta.safe_client._check_capital_shield") as mock_cs:
        mock_cs.return_value = {
            "gate": "capital_shield",
            "allowed": False,
            "reason": "test_block",
        }
        with patch("synapse.meta.safe_client._check_safety_middleware") as mock_sm:
            mock_sm.return_value = {
                "gate": "safety_middleware",
                "allowed": True,
                "reason": "passed",
            }

            client = MetaSafeClient(
                feature_flags=shared_flags,
                retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
                circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
                idempotency_store=IdempotencyStore.open(tmp_path / "idem.json"),
                ledger=Ledger.open(tmp_path / "ledger.ndjson"),
                config=MetaSafeClientConfig(),
            )

            result = client.create_campaign_safe(
                payload={"budget_mxn": "100"},
                idempotency_key="shared-flags-test",
            )

    assert result["ok"] is False
    assert "capital_shield" in result.get("blocked_by", [])
