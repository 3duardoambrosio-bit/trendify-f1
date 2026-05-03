from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from decimal import Decimal

import logging

import pytest

from synapse.meta.publisher_contracts import (
    FORBIDDEN_META_API_KEYS,
    MetaCampaignPayload,
    MetaCampaignResponse,
    MetaPauseRequest,
    MetaPauseResponse,
)


def test_campaign_payload_defaults_are_safe() -> None:
    p = MetaCampaignPayload(name="Launch A")
    assert p.name == "Launch A"
    assert p.objective == "OUTCOME_SALES"
    assert p.status == "PAUSED"
    assert p.budget_mxn is None
    assert p.daily_budget_minor_units is None
    assert p.targeting is None
    assert p.promoted_object is None
    assert dict(p.extra) == {}


def test_campaign_payload_is_frozen() -> None:
    p = MetaCampaignPayload(name="Launch A")
    with pytest.raises(FrozenInstanceError):
        p.status = "ACTIVE"  # type: ignore[misc]


def test_campaign_payload_to_api_dict_serializes_expected_shape() -> None:
    p = MetaCampaignPayload(
        name="Launch A",
        budget_mxn=Decimal("123.45"),
        daily_budget_minor_units=500,
        targeting={"geo_locations": {"countries": ["MX"]}},
        promoted_object={"pixel_id": "PX-1"},
        extra={"special_ad_categories": []},
    )
    out = p.to_api_dict()
    assert out["name"] == "Launch A"
    assert out["objective"] == "OUTCOME_SALES"
    assert out["status"] == "PAUSED"
    assert out["budget_mxn"] == "123.45"
    assert out["daily_budget_minor_units"] == 500
    assert out["targeting"] == {"geo_locations": {"countries": ["MX"]}}
    assert out["promoted_object"] == {"pixel_id": "PX-1"}
    assert out["special_ad_categories"] == []


def test_campaign_response_from_mock() -> None:
    r = MetaCampaignResponse.from_mock("MOCK_CAMP_123")
    assert r.ok is True
    assert r.campaign_id == "MOCK_CAMP_123"
    assert r.status == "PAUSED"
    assert r.mode == "mock"
    assert r.error_code is None
    assert r.error_message is None


def test_campaign_response_from_error() -> None:
    r = MetaCampaignResponse.from_error(
        "create_campaign_error",
        "network timeout",
        campaign_id=None,
        api_response={"raw": "x"},
    )
    assert r.ok is False
    assert r.campaign_id is None
    assert r.status == "PAUSED"
    assert r.mode == "error"
    assert r.error_code == "create_campaign_error"
    assert r.error_message == "network timeout"
    assert r.api_response == {"raw": "x"}


def test_pause_request_defaults_are_safe() -> None:
    req = MetaPauseRequest(campaign_id="camp-123")
    assert req.campaign_id == "camp-123"
    assert req.status == "PAUSED"
    assert req.to_api_dict() == {"campaign_id": "camp-123", "status": "PAUSED"}


def test_pause_response_from_mock() -> None:
    r = MetaPauseResponse.from_mock("camp-123")
    assert r.ok is True
    assert r.campaign_id == "camp-123"
    assert r.status == "PAUSED"
    assert r.mode == "mock"
    assert r.error_code is None
    assert r.error_message is None


def test_pause_response_from_error() -> None:
    r = MetaPauseResponse.from_error(
        "camp-123",
        "pause_campaign_error",
        "api unavailable",
        api_response={"raw": "y"},
    )
    assert r.ok is False
    assert r.campaign_id == "camp-123"
    assert r.status == "PAUSED"
    assert r.mode == "error"
    assert r.error_code == "pause_campaign_error"
    assert r.error_message == "api unavailable"
    assert r.api_response == {"raw": "y"}


@pytest.mark.parametrize("forbidden_key", sorted(FORBIDDEN_META_API_KEYS))
def test_campaign_payload_rejects_forbidden_meta_api_keys(forbidden_key: str) -> None:
    payload = MetaCampaignPayload(name="Forbidden Runtime Key", extra={forbidden_key: "legacy"})
    with pytest.raises(ValueError, match=forbidden_key):
        payload.to_api_dict()


@pytest.mark.parametrize("forbidden_key", sorted(FORBIDDEN_META_API_KEYS))
def test_pause_request_rejects_forbidden_meta_api_keys(forbidden_key: str) -> None:
    request = MetaPauseRequest(campaign_id="camp-123", extra={forbidden_key: "legacy"})
    with pytest.raises(ValueError, match=forbidden_key):
        request.to_api_dict()


@pytest.mark.parametrize("forbidden_key", sorted(FORBIDDEN_META_API_KEYS))
def test_campaign_payload_rejects_nested_forbidden_meta_api_keys(forbidden_key: str) -> None:
    payload = MetaCampaignPayload(
        name="Nested Forbidden Runtime Key",
        targeting={"geo_locations": {"countries": ["MX"]}, forbidden_key: "legacy"},
    )

    with pytest.raises(ValueError, match=forbidden_key):
        payload.to_api_dict()

def test_campaign_payload_rejects_forbidden_keys_inside_dataclass_targeting() -> None:
    @dataclass
    class NestedTargeting:
        instagram_actor_id: str

    payload = MetaCampaignPayload(
        name="Dataclass Forbidden",
        targeting={"nested": NestedTargeting(instagram_actor_id="legacy")},
    )

    with pytest.raises(ValueError) as exc:
        payload.to_api_dict()

    assert "MetaCampaignPayload" in str(exc.value)
    assert "$.targeting.nested.instagram_actor_id" in str(exc.value)


def test_campaign_payload_rejects_forbidden_keys_inside_custom_object_targeting() -> None:
    class NestedTargeting:
        def __init__(self) -> None:
            self.instagram_actor_id = "legacy"

    payload = MetaCampaignPayload(
        name="Custom Object Forbidden",
        targeting={"nested": NestedTargeting()},
    )

    with pytest.raises(ValueError) as exc:
        payload.to_api_dict()

    assert "MetaCampaignPayload" in str(exc.value)
    assert "$.targeting.nested.instagram_actor_id" in str(exc.value)


def test_campaign_payload_rejects_forbidden_keys_inside_pydantic_like_targeting() -> None:
    class PydanticLikeTargeting:
        def model_dump(self):
            return {"interests": ["legacy"]}

    payload = MetaCampaignPayload(
        name="Pydantic Like Forbidden",
        targeting={"nested": PydanticLikeTargeting()},
    )

    with pytest.raises(ValueError) as exc:
        payload.to_api_dict()

    assert "MetaCampaignPayload" in str(exc.value)
    assert "$.targeting.nested.interests" in str(exc.value)


def test_campaign_response_warns_on_deprecated_api_response_keys(caplog) -> None:
    caplog.set_level(logging.WARNING)

    response = MetaCampaignResponse.from_error(
        "create_campaign_error",
        "legacy echo",
        api_response={"data": {"instagram_actor_id": "legacy"}},
    )

    assert response.ok is False
    assert response.api_response == {"data": {"instagram_actor_id": "legacy"}}
    assert "deprecated_meta_response_keys_detected" in caplog.text
    assert "MetaCampaignResponse" in caplog.text
    assert "$.data.instagram_actor_id" in caplog.text


def test_pause_response_warns_on_deprecated_api_response_keys(caplog) -> None:
    caplog.set_level(logging.WARNING)

    response = MetaPauseResponse.from_error(
        "camp-123",
        "pause_campaign_error",
        "legacy echo",
        api_response={"data": {"interests": ["legacy"]}},
    )

    assert response.ok is False
    assert response.api_response == {"data": {"interests": ["legacy"]}}
    assert "deprecated_meta_response_keys_detected" in caplog.text
    assert "MetaPauseResponse" in caplog.text
    assert "$.data.interests" in caplog.text

def test_campaign_response_drift_emits_alert_sink_without_values(monkeypatch) -> None:
    from synapse.infra import alert_wiring

    calls = []

    class CaptureSink:
        def send(self, text, **kwargs):
            calls.append((text, kwargs))

    monkeypatch.setattr(alert_wiring, "get_alert_sink", lambda: CaptureSink())

    response = MetaCampaignResponse.from_error(
        "create_campaign_error",
        "legacy echo",
        api_response={"data": {"instagram_actor_id": "legacy"}},
    )

    assert response.ok is False
    assert len(calls) == 1

    text, kwargs = calls[0]
    assert "META_RESPONSE_DRIFT_DETECTED" in text
    assert "error_code=meta_response_drift_detected" in text
    assert "MetaCampaignResponse" in text
    assert "$.data.instagram_actor_id" in text
    assert "legacy" not in text

    assert kwargs["level"] == "WARN"
    assert kwargs["dedupe_key"].startswith("meta_response_drift:MetaCampaignResponse:")


def test_pause_response_drift_emits_alert_sink_without_values(monkeypatch) -> None:
    from synapse.infra import alert_wiring

    calls = []

    class CaptureSink:
        def send(self, text, **kwargs):
            calls.append((text, kwargs))

    monkeypatch.setattr(alert_wiring, "get_alert_sink", lambda: CaptureSink())

    response = MetaPauseResponse.from_error(
        "camp-123",
        "pause_campaign_error",
        "legacy echo",
        api_response={"data": {"interests": ["legacy"]}},
    )

    assert response.ok is False
    assert len(calls) == 1

    text, kwargs = calls[0]
    assert "META_RESPONSE_DRIFT_DETECTED" in text
    assert "error_code=meta_response_drift_detected" in text
    assert "MetaPauseResponse" in text
    assert "$.data.interests" in text
    assert "legacy" not in text

    assert kwargs["level"] == "WARN"
    assert kwargs["dedupe_key"].startswith("meta_response_drift:MetaPauseResponse:")
