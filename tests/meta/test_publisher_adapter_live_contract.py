from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from synapse.meta.publisher_adapter import call_create_campaign, call_pause_campaign
from synapse.meta.publisher_contracts import MetaCampaignPayload, MetaPauseRequest


def _live_env() -> dict[str, str]:
    return {
        "SYNAPSE_FLAG_META_LIVE_API": "1",
        "META_ACCESS_TOKEN": "tok_test_123",
        "META_AD_ACCOUNT_ID": "123456789",
    }


def test_create_campaign_off_mode_raises_not_implemented() -> None:
    with patch.dict(os.environ, {"SYNAPSE_FLAG_META_LIVE_API": "0"}, clear=False):
        with pytest.raises(NotImplementedError, match="Live Meta campaign creation"):
            call_create_campaign(MetaCampaignPayload(name="Adapter Contract"))


def test_pause_campaign_off_mode_raises_not_implemented() -> None:
    with patch.dict(os.environ, {"SYNAPSE_FLAG_META_LIVE_API": "0"}, clear=False):
        with pytest.raises(NotImplementedError, match="Live Meta campaign pause"):
            call_pause_campaign(MetaPauseRequest(campaign_id="camp-live"))


def test_create_campaign_live_posts_form_and_normalizes_ad_account() -> None:
    captured: dict[str, object] = {}

    def fake_post(url, fields):
        captured["url"] = url
        captured["fields"] = dict(fields)
        return {"id": "CAMP-123", "status": "ACTIVE"}

    payload = MetaCampaignPayload(
        name="Adapter Contract",
        extra={"special_ad_categories": ["NONE"]},
    )

    with patch.dict(os.environ, _live_env(), clear=False):
        with patch("synapse.meta.publisher_adapter._post_form", side_effect=fake_post):
            result = call_create_campaign(payload)

    assert captured["url"] == "https://graph.facebook.com/v25.0/act_123456789/campaigns"

    fields = captured["fields"]
    assert isinstance(fields, dict)
    assert fields["access_token"] == "tok_test_123"
    assert fields["name"] == "Adapter Contract"
    assert fields["status"] == "PAUSED"
    assert fields["special_ad_categories"] == ["NONE"]

    assert result["id"] == "CAMP-123"
    assert result["campaign_id"] == "CAMP-123"
    assert result["status"] == "ACTIVE"
    assert result["api_response"]["id"] == "CAMP-123"


def test_pause_campaign_live_posts_form_and_omits_campaign_id() -> None:
    captured: dict[str, object] = {}

    def fake_post(url, fields):
        captured["url"] = url
        captured["fields"] = dict(fields)
        return {"id": "camp-live", "status": "PAUSED"}

    req = MetaPauseRequest(
        campaign_id="camp-live",
        extra={"special_ad_categories": ["NONE"]},
    )

    with patch.dict(
        os.environ,
        {
            "SYNAPSE_FLAG_META_LIVE_API": "1",
            "META_ACCESS_TOKEN": "tok_test_123",
        },
        clear=False,
    ):
        with patch("synapse.meta.publisher_adapter._post_form", side_effect=fake_post):
            result = call_pause_campaign(req)

    assert captured["url"] == "https://graph.facebook.com/v25.0/camp-live"

    fields = captured["fields"]
    assert isinstance(fields, dict)
    assert fields["access_token"] == "tok_test_123"
    assert fields["status"] == "PAUSED"
    assert fields["special_ad_categories"] == ["NONE"]
    assert "campaign_id" not in fields

    assert result["id"] == "camp-live"
    assert result["campaign_id"] == "camp-live"
    assert result["status"] == "PAUSED"
    assert result["api_response"]["id"] == "camp-live"


def test_create_campaign_live_requires_access_token() -> None:
    with patch.dict(
        os.environ,
        {
            "SYNAPSE_FLAG_META_LIVE_API": "1",
            "META_AD_ACCOUNT_ID": "123456789",
        },
        clear=True,
    ):
        with pytest.raises(RuntimeError, match="META_ACCESS_TOKEN"):
            call_create_campaign(MetaCampaignPayload(name="Adapter Contract"))


def test_pause_campaign_live_requires_campaign_id() -> None:
    with patch.dict(
        os.environ,
        {
            "SYNAPSE_FLAG_META_LIVE_API": "1",
            "META_ACCESS_TOKEN": "tok_test_123",
        },
        clear=False,
    ):
        with pytest.raises(RuntimeError, match="campaign_id"):
            call_pause_campaign(MetaPauseRequest(campaign_id=""))
