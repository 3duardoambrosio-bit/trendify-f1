"""Tests for MetaSafeClient. S7: meta safe client."""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.infra.circuit_breaker import CircuitBreaker
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.idempotency_store import IdempotencyStore
from synapse.infra.ledger_f1_core import Ledger
from synapse.infra.retry_policy import RetryPolicy
from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig


def _make_client(
    tmp_path: Path,
    *,
    live: bool = False,
) -> MetaSafeClient:
    """Build a MetaSafeClient wired to tmp_path stores."""
    if live:
        flags = FeatureFlags(values={"meta_live_api": True})
    else:
        flags = FeatureFlags(values={})

    return MetaSafeClient(
        feature_flags=flags,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
        idempotency_store=IdempotencyStore.open(tmp_path / "idem.json"),
        ledger=Ledger.open(tmp_path / "ledger.ndjson"),
        config=MetaSafeClientConfig(),
    )


def _read_ledger_events(tmp_path: Path) -> list[dict]:
    p = tmp_path / "ledger.ndjson"
    if not p.exists():
        return []
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


# ------------------------------------------------------------------
# 1) meta_live_api OFF => mock mode, status PAUSED forced
# ------------------------------------------------------------------
class TestCreateCampaignMock:
    def test_mock_returns_paused(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        result = client.create_campaign_safe(
            payload={"name": "Test Campaign", "status": "ACTIVE"},
            idempotency_key="test-key-001",
            correlation_id="corr-001",
        )
        assert result["ok"] is True
        assert result["mode"] == "mock"
        assert result["status"] == "PAUSED"
        assert "campaign_id" in result
        assert result["campaign_id"].startswith("MOCK_CAMP_")

    def test_ledger_events_written(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        client.create_campaign_safe(
            payload={"name": "Test"},
            idempotency_key="test-key-002",
            correlation_id="corr-002",
        )
        events = _read_ledger_events(tmp_path)
        event_types = [e["event_type"] for e in events]
        assert "meta.create_campaign.attempt" in event_types
        assert "meta.create_campaign.result" in event_types


# ------------------------------------------------------------------
# 2) Idempotency: same key => cached, no duplicate
# ------------------------------------------------------------------
class TestIdempotency:
    def test_duplicate_key_returns_cached(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        r1 = client.create_campaign_safe(
            payload={"name": "Camp A"},
            idempotency_key="idem-key-1",
            correlation_id="corr-a",
        )
        r2 = client.create_campaign_safe(
            payload={"name": "Camp A different"},
            idempotency_key="idem-key-1",
            correlation_id="corr-b",
        )
        assert r2["mode"] == "cached"
        assert r2["result"]["campaign_id"] == r1["campaign_id"]

        # Only 1 attempt+result pair in ledger (second call is cached)
        events = _read_ledger_events(tmp_path)
        attempt_events = [
            e for e in events if e["event_type"] == "meta.create_campaign.attempt"
        ]
        assert len(attempt_events) == 1


# ------------------------------------------------------------------
# 3) Autopause: spend >= 80% cap => PAUSE
# ------------------------------------------------------------------
class TestAutopause:
    def test_at_threshold_triggers_pause(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        result = client.maybe_autopause(
            spend_today_mxn=Decimal("80"),
            cap_mxn=Decimal("100"),
            campaign_id="camp-123",
            correlation_id="corr-ap",
        )
        assert result["ok"] is True
        assert result["action"] == "PAUSE"

    def test_below_threshold_no_pause(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        result = client.maybe_autopause(
            spend_today_mxn=Decimal("50"),
            cap_mxn=Decimal("100"),
            campaign_id="camp-456",
            correlation_id="corr-np",
        )
        assert result["ok"] is True
        assert result["action"] == "NONE"

    def test_autopause_ledger_events(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        client.maybe_autopause(
            spend_today_mxn=Decimal("85"),
            cap_mxn=Decimal("100"),
            campaign_id="camp-789",
        )
        events = _read_ledger_events(tmp_path)
        event_types = [e["event_type"] for e in events]
        assert "meta.autopause.attempt" in event_types
        assert "meta.autopause.result" in event_types


# ------------------------------------------------------------------
# 4) Error path: live mode + publisher raises => meta.error in ledger
# ------------------------------------------------------------------
class TestErrorPath:
    def test_live_publisher_error_captured(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=True)

        # publisher_adapter.call_create_campaign raises NotImplementedError
        # which is the default behavior; retry will exhaust and propagate
        result = client.create_campaign_safe(
            payload={"name": "Will Fail"},
            idempotency_key="error-key-1",
            correlation_id="corr-err",
        )
        assert result["ok"] is False
        assert "error_code" in result
        assert result["error_code"] == "create_campaign_error"

        events = _read_ledger_events(tmp_path)
        event_types = [e["event_type"] for e in events]
        assert "meta.error" in event_types

    def test_live_publisher_custom_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=True)

        with patch(
            "synapse.meta.safe_client.call_create_campaign",
            side_effect=ConnectionError("graph.facebook.com unreachable"),
        ):
            result = client.create_campaign_safe(
                payload={"name": "Conn Fail"},
                idempotency_key="error-key-2",
                correlation_id="corr-err2",
            )

        assert result["ok"] is False
        assert "unreachable" in result["error_message"]

        events = _read_ledger_events(tmp_path)
        error_events = [e for e in events if e["event_type"] == "meta.error"]
        assert len(error_events) >= 1


# ------------------------------------------------------------------
# 5) Cockpit still works (regression)
# ------------------------------------------------------------------
class TestCockpitRegression:
    def test_cockpit_health_json_parseable(self) -> None:
        r = subprocess.run(
            [sys.executable, "-m", "synapse.cli.cockpit", "health", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        obj = json.loads(r.stdout)
        assert obj["ok"] is True
        assert obj["mode"] == "health"
