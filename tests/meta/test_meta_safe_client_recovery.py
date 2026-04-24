"""Regression tests for governed-ledger recovery in MetaSafeClient."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from synapse.infra.circuit_breaker import CircuitBreaker
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.retry_policy import RetryPolicy
from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig


def _make_client(tmp_path: Path, *, live: bool = False) -> MetaSafeClient:
    flags = FeatureFlags(values={"meta_live_api": True}) if live else FeatureFlags(values={})
    return MetaSafeClient(
        feature_flags=flags,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
        idempotency_store=SimpleNamespace(path=tmp_path / "idem.sqlite3"),
        ledger=SimpleNamespace(path=tmp_path / "ledger.ndjson"),
        config=MetaSafeClientConfig(),
    )


def _append_ledger_event(tmp_path: Path, event: dict) -> None:
    ledger_path = tmp_path / "ledger.ndjson"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


class TestGovernedLedgerRecovery:
    def test_create_campaign_recovers_from_governed_ledger_on_in_flight(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        idem_key = "idem-recover-create"
        correlation_id = "corr-recover-create"

        _append_ledger_event(
            tmp_path,
            {
                "event_type": "meta.create_campaign.result",
                "correlation_id": correlation_id,
                "idempotency_key": idem_key,
                "payload": {
                    "ok": True,
                    "mode": "mock",
                    "campaign_id": "camp-recovered-001",
                    "status": "PAUSED",
                },
            },
        )

        with patch(
            "synapse.meta.safe_client.execute_once",
            return_value={"status": "IN_FLIGHT", "response": None},
        ):
            result = client.create_campaign_safe(
                payload={"name": "Recover Campaign"},
                idempotency_key=idem_key,
                correlation_id=correlation_id,
            )

        assert result["ok"] is True
        assert result["campaign_id"] == "camp-recovered-001"
        assert result["status"] == "PAUSED"
        assert result["mode"] == "mock"
        assert result["recovered_from"] == "governed_ledger"
        assert result["idempotency_status"] == "IN_FLIGHT"
        assert result["idempotency_key"] == idem_key
        assert result["correlation_id"] == correlation_id

    def test_maybe_autopause_recovers_from_governed_ledger_on_conflict(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        spend_today = Decimal("85")
        cap_mxn = Decimal("100")
        campaign_id = "camp-recovered-002"
        correlation_id = "corr-recover-autopause"
        idem_key = f"autopause:{campaign_id}:{spend_today}"

        _append_ledger_event(
            tmp_path,
            {
                "event_type": "meta.autopause.result",
                "correlation_id": correlation_id,
                "idempotency_key": idem_key,
                "payload": {
                    "ok": True,
                    "action": "PAUSE",
                    "mode": "mock",
                    "reason": "spend_at_or_above_threshold",
                    "spend_today_mxn": str(spend_today),
                    "threshold_mxn": str(cap_mxn * client.config.autopause_ratio),
                    "campaign_id": campaign_id,
                },
            },
        )

        with patch(
            "synapse.meta.safe_client.execute_once",
            return_value={"status": "CONFLICT", "response": None},
        ):
            result = client.maybe_autopause(
                spend_today_mxn=spend_today,
                cap_mxn=cap_mxn,
                campaign_id=campaign_id,
                correlation_id=correlation_id,
            )

        assert result["ok"] is True
        assert result["action"] == "PAUSE"
        assert result["campaign_id"] == campaign_id
        assert result["mode"] == "mock"
        assert result["recovered_from"] == "governed_ledger"
        assert result["idempotency_status"] == "CONFLICT"
        assert result["correlation_id"] == correlation_id
