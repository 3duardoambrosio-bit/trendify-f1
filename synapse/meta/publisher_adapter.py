"""Adapter wrapping the existing Meta publisher for safe_client use. S7."""

from __future__ import annotations

from typing import Any, Dict


def call_create_campaign(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call the real Meta Graph API to create a campaign.

    This is the LIVE path, only invoked when meta_live_api flag is ON.
    Currently raises NotImplementedError because real invocation requires
    credentials, ad-account setup, and the full publish pipeline.
    """
    raise NotImplementedError(
        "Live Meta campaign creation requires META_ACCESS_TOKEN and "
        "META_AD_ACCOUNT_ID. Use the full publish pipeline "
        "(synapse.meta_publish_execute --mode live) or ensure "
        "SYNAPSE_FLAG_META_LIVE_API is OFF (default) for mock mode."
    )


def call_pause_campaign(campaign_id: str) -> Dict[str, Any]:
    """Call the real Meta Graph API to pause a campaign.

    This is the LIVE path, only invoked when meta_live_api flag is ON.
    """
    raise NotImplementedError(
        "Live Meta campaign pause requires META_ACCESS_TOKEN. "
        "Ensure SYNAPSE_FLAG_META_LIVE_API is OFF (default) for mock mode."
    )
