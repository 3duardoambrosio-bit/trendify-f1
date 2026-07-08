"""Tests for MetaSafeClient."""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from synapse.infra.circuit_breaker import CircuitBreaker, CircuitOpenError
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


def _read_ledger_events(tmp_path: Path) -> list[dict]:
    p = tmp_path / "ledger.ndjson"
    if not p.exists():
        return []
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


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


class TestIdempotency:
    def test_duplicate_key_returns_cached(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        r1 = client.create_campaign_safe(
            payload={"name": "Camp A"},
            idempotency_key="idem-key-1",
            correlation_id="corr-a",
        )
        r2 = client.create_campaign_safe(
            payload={"name": "Camp A"},
            idempotency_key="idem-key-1",
            correlation_id="corr-b",
        )
        assert r2["ok"] is True
        assert r2["mode"] == "cached"
        assert r2["result"]["campaign_id"] == r1["campaign_id"]

        events = _read_ledger_events(tmp_path)
        attempt_events = [e for e in events if e["event_type"] == "meta.create_campaign.attempt"]
        assert len(attempt_events) == 1

    def test_duplicate_key_never_reruns_spend_gates(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        with patch(
            "synapse.meta.safe_client._check_capital_shield",
            return_value={
                "gate": "capital_shield",
                "allowed": True,
                "reason": "approved",
                "correlation_id": "corr-idem-gate",
            },
        ) as mock_cs, patch(
            "synapse.meta.safe_client._check_safety_middleware",
            return_value={
                "gate": "safety_middleware",
                "allowed": True,
                "reason": "approved",
                "correlation_id": "corr-idem-gate",
            },
        ) as mock_sm:
            r1 = client.create_campaign_safe(
                payload={"name": "Camp Gate", "budget_mxn": "50"},
                idempotency_key="idem-gate-1",
                correlation_id="corr-g1",
            )
            r2 = client.create_campaign_safe(
                payload={"name": "Camp Gate", "budget_mxn": "50"},
                idempotency_key="idem-gate-1",
                correlation_id="corr-g2",
            )

        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r2["mode"] == "cached"
        # The capital shield debits the vault (request_spend): a replay of the
        # same idempotency_key must be answered from the idempotency store
        # without running the spend gates (and the vault) again.
        assert mock_cs.call_count == 1
        assert mock_sm.call_count == 1

    def test_same_key_different_payload_returns_conflict(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        r1 = client.create_campaign_safe(
            payload={"name": "Camp A"},
            idempotency_key="idem-key-conflict",
            correlation_id="corr-c1",
        )
        r2 = client.create_campaign_safe(
            payload={"name": "Camp B"},
            idempotency_key="idem-key-conflict",
            correlation_id="corr-c2",
        )

        assert r1["ok"] is True
        assert r2["ok"] is False
        assert r2["error_code"] == "idempotency_conflict"

        events = _read_ledger_events(tmp_path)
        attempt_events = [e for e in events if e["event_type"] == "meta.create_campaign.attempt"]
        assert len(attempt_events) == 1


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

    def test_autopause_duplicate_same_spend_returns_cached(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        r1 = client.maybe_autopause(
            spend_today_mxn=Decimal("85"),
            cap_mxn=Decimal("100"),
            campaign_id="camp-dup",
            correlation_id="corr-ap-1",
        )
        r2 = client.maybe_autopause(
            spend_today_mxn=Decimal("85"),
            cap_mxn=Decimal("100"),
            campaign_id="camp-dup",
            correlation_id="corr-ap-2",
        )

        assert r1["ok"] is True
        assert r1["action"] == "PAUSE"
        assert r2["ok"] is True
        assert r2["mode"] == "cached"
        assert r2["action"] == "PAUSE"

        events = _read_ledger_events(tmp_path)
        attempt_events = [e for e in events if e["event_type"] == "meta.autopause.attempt"]
        assert len(attempt_events) == 1


class TestErrorPath:
    def test_live_publisher_error_captured(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=True)

        result = client.create_campaign_safe(
            payload={"name": "Will Fail"},
            idempotency_key="error-key-1",
            correlation_id="corr-err",
        )
        assert result["ok"] is False
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


class TestPreSpendGates:
    def test_gates_pass_by_default_mock_mode(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        result = client.create_campaign_safe(
            payload={"name": "Gated Campaign", "budget_mxn": "50"},
            idempotency_key="gate-pass-001",
            correlation_id="corr-gate-pass",
        )
        assert result["ok"] is True
        assert result["mode"] == "mock"

    def test_capital_shield_blocks_campaign(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        with patch(
            "synapse.meta.safe_client._check_capital_shield",
            return_value={
                "gate": "capital_shield",
                "allowed": False,
                "allocated": "0",
                "reason": "not_approved",
                "correlation_id": "corr-cs-block",
            },
        ):
            result = client.create_campaign_safe(
                payload={"name": "Blocked Campaign", "budget_mxn": "200"},
                idempotency_key="gate-block-001",
                correlation_id="corr-cs-block",
            )
        assert result["ok"] is False
        assert result["error_code"] == "pre_spend_gate_blocked"
        assert "capital_shield" in result["blocked_by"]

        events = _read_ledger_events(tmp_path)
        blocked_events = [e for e in events if e["event_type"] == "meta.create_campaign.blocked"]
        assert len(blocked_events) >= 1

    def test_safety_middleware_blocks_campaign(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        with patch(
            "synapse.meta.safe_client._check_safety_middleware",
            return_value={
                "gate": "safety_middleware",
                "allowed": False,
                "reason": "KILLSWITCH_ACTIVE",
                "correlation_id": "corr-sm-block",
            },
        ):
            result = client.create_campaign_safe(
                payload={"name": "SM Blocked", "budget_mxn": "50"},
                idempotency_key="gate-block-002",
                correlation_id="corr-sm-block",
            )
        assert result["ok"] is False
        assert "safety_middleware" in result["blocked_by"]


class TestLedgerCriticalFlag:
    def test_create_campaign_ledger_has_critical_true(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        client.create_campaign_safe(
            payload={"name": "Critical Test"},
            idempotency_key="crit-key-001",
            correlation_id="corr-crit",
        )
        events = _read_ledger_events(tmp_path)
        for event in events:
            assert event.get("critical") is True

    def test_autopause_ledger_has_critical_true(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)
        client.maybe_autopause(
            spend_today_mxn=Decimal("85"),
            cap_mxn=Decimal("100"),
            campaign_id="camp-crit-ap",
        )
        events = _read_ledger_events(tmp_path)
        for event in events:
            assert event.get("critical") is True

    def test_error_path_ledger_has_critical_true(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=True)
        client.create_campaign_safe(
            payload={"name": "Will Fail"},
            idempotency_key="crit-err-001",
            correlation_id="corr-crit-err",
        )
        events = _read_ledger_events(tmp_path)
        for event in events:
            assert event.get("critical") is True


class TestCockpitRegression:
    def test_cockpit_health_json_parseable(self) -> None:
        r = subprocess.run(
            [sys.executable, "-m", "synapse.cli.cockpit", "health", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        obj = json.loads(r.stdout)
        assert obj["ok"] is True


def test_governed_anchor_is_written_into_ledger_events(tmp_path: Path) -> None:
    client = _make_client(tmp_path, live=False)
    client.create_campaign_safe(
        payload={"name": "Governed Anchor Campaign"},
        idempotency_key="test-key-anchor-001",
        correlation_id="corr-anchor-001",
    )

    events = _read_ledger_events(tmp_path)
    attempt = next(e for e in events if e["event_type"] == "meta.create_campaign.attempt")

    assert "governed_anchor" in attempt["payload"]
    anchor = attempt["payload"]["governed_anchor"]
    assert anchor["payload"]["event_type"] == "meta.create_campaign.attempt"
    assert anchor["payload"]["correlation_id"] == "corr-anchor-001"
    assert anchor["payload"]["idempotency_key"] == "test-key-anchor-001"
    assert anchor["metadata"]["anchor_contract_version"] == "governed-write-anchor.v1"
    assert anchor["metadata"]["source"] == "synapse.meta.safe_client"


class TestErrorTaxonomy:
    def test_live_autopause_circuit_open_returns_circuit_open(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=True)

        with patch.object(client.circuit_breaker, "call", side_effect=CircuitOpenError("breaker open")):
            result = client.maybe_autopause(
                spend_today_mxn=Decimal("80"),
                cap_mxn=Decimal("100"),
                campaign_id="camp-cb-open",
                correlation_id="corr-cb-open",
            )

        assert result["ok"] is False
        assert result["error_code"] == "circuit_open"
        assert result["error_type"] == "CircuitOpenError"

    def test_live_autopause_pause_failure_returns_autopause_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=True)

        with patch(
            "synapse.meta.safe_client.call_pause_campaign",
            side_effect=ConnectionError("pause unreachable"),
        ):
            result = client.maybe_autopause(
                spend_today_mxn=Decimal("80"),
                cap_mxn=Decimal("100"),
                campaign_id="camp-pause-fail",
                correlation_id="corr-pause-fail",
            )

        assert result["ok"] is False
        assert result["error_code"] == "autopause_error"
        assert result["error_type"] == "ConnectionError"
        assert "pause unreachable" in result["error_message"]

    def test_create_campaign_in_flight_maps_specific_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        with patch(
            "synapse.meta.safe_client.execute_once",
            return_value={"status": "IN_FLIGHT", "response": None},
        ):
            result = client.create_campaign_safe(
                payload={"name": "Inflight"},
                idempotency_key="idem-in-flight-create",
                correlation_id="corr-in-flight-create",
            )

        assert result["ok"] is False
        assert result["error_code"] == "idempotency_in_flight"

    def test_create_campaign_unexpected_status_maps_specific_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        with patch(
            "synapse.meta.safe_client.execute_once",
            return_value={"status": "BROKEN", "response": None},
        ):
            result = client.create_campaign_safe(
                payload={"name": "Unexpected"},
                idempotency_key="idem-unexpected-create",
                correlation_id="corr-unexpected-create",
            )

        assert result["ok"] is False
        assert result["error_code"] == "idempotency_unexpected_status"

    def test_autopause_in_flight_maps_specific_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        with patch(
            "synapse.meta.safe_client.execute_once",
            return_value={"status": "IN_FLIGHT", "response": None},
        ):
            result = client.maybe_autopause(
                spend_today_mxn=Decimal("85"),
                cap_mxn=Decimal("100"),
                campaign_id="camp-in-flight",
                correlation_id="corr-in-flight",
            )

        assert result["ok"] is False
        assert result["error_code"] == "idempotency_in_flight"

    def test_autopause_unexpected_status_maps_specific_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, live=False)

        with patch(
            "synapse.meta.safe_client.execute_once",
            return_value={"status": "BROKEN", "response": None},
        ):
            result = client.maybe_autopause(
                spend_today_mxn=Decimal("85"),
                cap_mxn=Decimal("100"),
                campaign_id="camp-unexpected",
                correlation_id="corr-unexpected",
            )

        assert result["ok"] is False
        assert result["error_code"] == "idempotency_unexpected_status"

def test_capital_shield_gate_internal_exception_fails_closed(tmp_path: Path, monkeypatch) -> None:
    client = _make_client(tmp_path)
    monkeypatch.setattr(type(client), "_is_live", property(lambda self: False), raising=True)

    class BoomShield:
        def __init__(self, *args, **kwargs):
            pass

        def decide_for_product(self, *args, **kwargs):
            raise RuntimeError("boom")

    with patch("vault.vault_file_backed.VaultFileBacked", return_value=object()):
        with patch("ops.capital_shield_v2.CapitalShieldV2", BoomShield):
            with patch("synapse.meta.safe_client._check_safety_middleware") as mock_sm:
                mock_sm.return_value = {
                    "gate": "safety_middleware",
                    "allowed": True,
                    "reason": "passed",
                    "correlation_id": "corr-1",
                }

                result = client.create_campaign_safe(
                    {"name": "Camp", "budget_mxn": "100"},
                    idempotency_key="idem-cs-explosion",
                    correlation_id="corr-1",
                )

    assert result["ok"] is False
    assert result["error_code"] == "pre_spend_gate_blocked"
    assert "capital_shield" in result["blocked_by"]
    assert result["capital_shield"]["reason"] == "gate_execution_error:RuntimeError"

def test_safety_middleware_gate_internal_exception_fails_closed(tmp_path: Path, monkeypatch) -> None:
    client = _make_client(tmp_path)
    monkeypatch.setattr(type(client), "_is_live", property(lambda self: False), raising=True)

    with patch("synapse.meta.safe_client._check_capital_shield") as mock_cs:
        mock_cs.return_value = {
            "gate": "capital_shield",
            "allowed": True,
            "reason": "approved",
            "correlation_id": "corr-2",
        }
        with patch("ops.safety_middleware.check_safety_before_spend", side_effect=RuntimeError("boom")):
            result = client.create_campaign_safe(
                {"name": "Camp", "budget_mxn": "100"},
                idempotency_key="idem-sm-explosion",
                correlation_id="corr-2",
            )

    assert result["ok"] is False
    assert result["error_code"] == "pre_spend_gate_blocked"
    assert "safety_middleware" in result["blocked_by"]
    assert result["safety_middleware"]["reason"] == "gate_execution_error:RuntimeError"

def test_capital_shield_uses_vault_error_when_vault_state_corrupted(tmp_path: Path, monkeypatch) -> None:
    from synapse.meta.safe_client import _check_capital_shield

    state_file = tmp_path / "vault_state.json"
    state_file.write_text("THIS IS NOT JSON {{{{", encoding="utf-8")
    monkeypatch.setenv("SYNAPSE_VAULT_STATE_FILE", str(state_file))

    result = _check_capital_shield(Decimal("10"), "corr-vault-state")

    assert result["gate"] == "capital_shield"
    assert result["allowed"] is False
    assert result["reason"] == "vault_error"

