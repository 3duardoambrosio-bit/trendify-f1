"""Adapter wrapping the existing Meta publisher for safe_client use. S7."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from synapse.meta.publisher_contracts import MetaCampaignPayload, MetaPauseRequest


def _campaign_payload_to_api_dict(payload: MetaCampaignPayload | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(payload, MetaCampaignPayload):
        return payload.to_api_dict()
    return dict(payload)


def _pause_request_to_api_dict(request: MetaPauseRequest | str) -> Dict[str, Any]:
    if isinstance(request, MetaPauseRequest):
        return request.to_api_dict()
    return {"campaign_id": str(request), "status": "PAUSED"}


def call_create_campaign(payload: MetaCampaignPayload | Mapping[str, Any]) -> Dict[str, Any]:
    """Call the real Meta Graph API to create a campaign.

    This is the LIVE path, only invoked when meta_live_api flag is ON.
    Currently raises NotImplementedError because real invocation requires
    credentials, ad-account setup, and the full publish pipeline.
    """
    _payload = _campaign_payload_to_api_dict(payload)
    _ = _payload
    raise NotImplementedError(
        "Live Meta campaign creation requires META_ACCESS_TOKEN and "
        "META_AD_ACCOUNT_ID. Use the full publish pipeline "
        "(synapse.meta_publish_execute --mode live) or ensure "
        "SYNAPSE_FLAG_META_LIVE_API is OFF (default) for mock mode."
    )


def call_pause_campaign(request: MetaPauseRequest | str) -> Dict[str, Any]:
    """Call the real Meta Graph API to pause a campaign.

    This is the LIVE path, only invoked when meta_live_api flag is ON.
    """
    _request = _pause_request_to_api_dict(request)
    _ = _request
    raise NotImplementedError(
        "Live Meta campaign pause requires META_ACCESS_TOKEN. "
        "Ensure SYNAPSE_FLAG_META_LIVE_API is OFF (default) for mock mode."
    )
