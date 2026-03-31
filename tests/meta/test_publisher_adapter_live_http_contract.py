from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs
from unittest.mock import patch

import pytest

from synapse.integrations.http_client import HttpResponseError
from synapse.meta.publisher_adapter import call_create_campaign, call_pause_campaign
from synapse.meta.publisher_contracts import MetaCampaignPayload, MetaPauseRequest


def _capture_request_factory():
    captured: dict[str, object] = {}

    class _FakeClient:
        def request(self, req):
            captured["request"] = req
            return SimpleNamespace(
                status=200,
                headers={"content-type": "application/json"},
                body=b'{"id":"CAMP-123","status":"PAUSED"}',
            )

    return captured, _FakeClient()


def test_call_create_campaign_posts_form_encoded_payload(monkeypatch):
    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "1")
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_live_123")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")
    monkeypatch.setenv("META_GRAPH_VERSION", "v25.0")

    captured, fake_client = _capture_request_factory()

    payload = MetaCampaignPayload(
        name="Live Contract",
        extra={"special_ad_categories": ["NONE"]},
    )

    with patch("synapse.meta.publisher_adapter._build_http_client", return_value=fake_client):
        result = call_create_campaign(payload)

    req = captured["request"]
    assert req.method == "POST"
    assert req.url == "https://graph.facebook.com/v25.0/act_123456789/campaigns"
    assert req.headers["Content-Type"].startswith("application/x-www-form-urlencoded")

    fields = parse_qs(req.body.decode("utf-8"))
    assert fields["access_token"] == ["tok_live_123"]
    assert fields["name"] == ["Live Contract"]
    assert fields["status"] == ["PAUSED"]
    assert fields["objective"] == ["OUTCOME_SALES"]
    assert fields["special_ad_categories"] == ['["NONE"]']

    assert result["campaign_id"] == "CAMP-123"
    assert result["id"] == "CAMP-123"
    assert result["status"] == "PAUSED"


def test_call_pause_campaign_posts_pause_request(monkeypatch):
    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "1")
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_live_456")
    monkeypatch.setenv("META_GRAPH_VERSION", "v25.0")

    captured: dict[str, object] = {}

    class _FakeClient:
        def request(self, req):
            captured["request"] = req
            return SimpleNamespace(
                status=200,
                headers={"content-type": "application/json"},
                body=b'{"success":true}',
            )

    with patch("synapse.meta.publisher_adapter._build_http_client", return_value=_FakeClient()):
        result = call_pause_campaign(MetaPauseRequest(campaign_id="camp-live-1"))

    req = captured["request"]
    assert req.method == "POST"
    assert req.url == "https://graph.facebook.com/v25.0/camp-live-1"

    fields = parse_qs(req.body.decode("utf-8"))
    assert fields["access_token"] == ["tok_live_456"]
    assert fields["status"] == ["PAUSED"]

    assert result["campaign_id"] == "camp-live-1"
    assert result["id"] == "camp-live-1"
    assert result["status"] == "PAUSED"


def test_call_create_campaign_wraps_http_error(monkeypatch):
    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "1")
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_live_789")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "act_999")

    class _FakeClient:
        def request(self, req):
            raise HttpResponseError(
                status=400,
                body=b'{"error":{"message":"Invalid parameter","code":100}}',
                message="Client error",
            )

    with patch("synapse.meta.publisher_adapter._build_http_client", return_value=_FakeClient()):
        with pytest.raises(RuntimeError) as ex:
            call_create_campaign({"name": "Bad Campaign", "status": "PAUSED"})

    msg = str(ex.value)
    assert "status=400" in msg
    assert "Invalid parameter" in msg
