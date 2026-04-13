from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from synapse.infra.circuit_breaker import CircuitBreaker
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.retry_policy import RetryPolicy
from synapse.meta.publisher_adapter import call_create_campaign, call_pause_campaign
from synapse.meta.publisher_contracts import MetaCampaignPayload, MetaPauseRequest
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


def test_safe_client_mock_accepts_meta_campaign_payload(tmp_path: Path) -> None:
    client = _make_client(tmp_path, live=False)
    payload = MetaCampaignPayload(name="Contract Mock", budget_mxn=Decimal("10.00"))
    result = client.create_campaign_safe(
        payload=payload,
        idempotency_key="contract-mock",
        correlation_id="corr-contract-mock",
    )
    assert result["ok"] is True
    assert result["mode"] == "mock"
    assert result["status"] == "PAUSED"
    assert result["campaign_id"].startswith("MOCK_CAMP_")


def test_safe_client_live_converts_dict_payload_to_contract(tmp_path: Path) -> None:
    client = _make_client(tmp_path, live=True)
    captured = {}

    def fake_create(arg):
        captured["payload"] = arg
        return {"id": "CAMP-123", "status": "PAUSED"}

    with patch("synapse.meta.safe_client.call_create_campaign", side_effect=fake_create):
        result = client.create_campaign_safe(
            payload={"name": "Live Dict", "status": "ACTIVE", "special_ad_categories": []},
            idempotency_key="contract-live-dict",
            correlation_id="corr-live-dict",
        )

    sent = captured["payload"]
    assert isinstance(sent, MetaCampaignPayload)
    assert sent.name == "Live Dict"
    assert sent.status == "PAUSED"
    assert dict(sent.extra)["special_ad_categories"] == []
    assert result["ok"] is True
    assert result["campaign_id"] == "CAMP-123"


def test_safe_client_live_accepts_contract_payload_directly(tmp_path: Path) -> None:
    client = _make_client(tmp_path, live=True)
    captured = {}

    def fake_create(arg):
        captured["payload"] = arg
        return {"id": "CAMP-456", "status": "PAUSED"}

    payload = MetaCampaignPayload(
        name="Live Contract",
        extra={"special_ad_categories": ["NONE"]},
    )

    with patch("synapse.meta.safe_client.call_create_campaign", side_effect=fake_create):
        result = client.create_campaign_safe(
            payload=payload,
            idempotency_key="contract-live-direct",
            correlation_id="corr-live-direct",
        )

    sent = captured["payload"]
    assert isinstance(sent, MetaCampaignPayload)
    assert sent.name == "Live Contract"
    assert sent.status == "PAUSED"
    assert dict(sent.extra)["special_ad_categories"] == ["NONE"]
    assert result["ok"] is True
    assert result["api_response"]["id"] == "CAMP-456"


def test_safe_client_live_autopause_forwards_pause_request(tmp_path: Path) -> None:
    client = _make_client(tmp_path, live=True)
    captured = {}

    def fake_pause(arg):
        captured["request"] = arg
        return {"id": "camp-live", "status": "PAUSED"}

    with patch("synapse.meta.safe_client.call_pause_campaign", side_effect=fake_pause):
        result = client.maybe_autopause(
            spend_today_mxn=Decimal("80"),
            cap_mxn=Decimal("100"),
            campaign_id="camp-live",
            correlation_id="corr-live-pause",
        )

    req = captured["request"]
    assert isinstance(req, MetaPauseRequest)
    assert req.campaign_id == "camp-live"
    assert result["ok"] is True
    assert result["action"] == "PAUSE"
    assert result["mode"] == "live"


def test_publisher_adapter_accepts_contract_payload_shape() -> None:
    try:
        call_create_campaign(MetaCampaignPayload(name="Adapter Contract"))
    except NotImplementedError as exc:
        assert "Live Meta campaign creation" in str(exc)
    else:
        raise AssertionError("Expected NotImplementedError")


def test_publisher_adapter_accepts_pause_request_shape() -> None:
    try:
        call_pause_campaign(MetaPauseRequest(campaign_id="camp-live"))
    except NotImplementedError as exc:
        assert "Live Meta campaign pause" in str(exc)
    else:
        raise AssertionError("Expected NotImplementedError")
