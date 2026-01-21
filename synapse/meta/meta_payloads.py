# synapse/meta/meta_payloads.py
"""
Meta Payloads — OLEADA 19
========================

Genera payload base (no API call) + validación.
Sirve para que CampaignBlueprint / Ads Intelligence lo usen sin romper.

Nota:
- Esto NO sube campañas. Solo prepara estructura consistente y validada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class MetaPayloadError(Exception):
    pass


ALLOWED_OBJECTIVES = {"OUTCOME_SALES", "OUTCOME_LEADS", "OUTCOME_ENGAGEMENT"}
ALLOWED_BUDGET_TYPES = {"daily", "lifetime"}


def build_meta_campaign_payload(
    *,
    product_id: str,
    product_name: str,
    objective: str = "OUTCOME_SALES",
    budget_type: str = "daily",
    budget_usd: float = 10.0,
    geo: Optional[List[str]] = None,
    age_min: int = 18,
    age_max: int = 45,
    placements: Optional[List[str]] = None,
    utm_source: str = "meta",
    utm_medium: str = "paid_social",
    utm_campaign: Optional[str] = None,
) -> Dict[str, Any]:
    geo = geo or ["MX"]
    placements = placements or ["feed", "stories", "reels"]
    utm_campaign = utm_campaign or f"trendify_{product_id}"

    payload = {
        "schema_version": "1.0.0",
        "platform": "meta",
        "product": {"product_id": product_id, "product_name": product_name},
        "campaign": {
            "objective": objective,
            "budget_type": budget_type,
            "budget_usd": float(budget_usd),
        },
        "adset": {
            "targeting": {
                "geo": geo,
                "age_min": int(age_min),
                "age_max": int(age_max),
                "placements": placements,
            }
        },
        "tracking": {
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
        },
    }
    validate_meta_payload(payload)
    return payload


def validate_meta_payload(payload: Dict[str, Any]) -> None:
    try:
        campaign = payload["campaign"]
        obj = campaign["objective"]
        if obj not in ALLOWED_OBJECTIVES:
            raise MetaPayloadError(f"objective not allowed: {obj}")

        bt = campaign["budget_type"]
        if bt not in ALLOWED_BUDGET_TYPES:
            raise MetaPayloadError(f"budget_type not allowed: {bt}")

        b = float(campaign["budget_usd"])
        if b <= 0:
            raise MetaPayloadError("budget_usd must be > 0")

        tgt = payload["adset"]["targeting"]
        if not tgt["geo"]:
            raise MetaPayloadError("geo required")
        if tgt["age_min"] < 13 or tgt["age_max"] > 65 or tgt["age_min"] > tgt["age_max"]:
            raise MetaPayloadError("invalid age range")

        placements = tgt.get("placements") or []
        if not isinstance(placements, list) or len(placements) == 0:
            raise MetaPayloadError("placements required")

        # tracking
        tr = payload["tracking"]
        for k in ("utm_source", "utm_medium", "utm_campaign"):
            if not str(tr.get(k) or "").strip():
                raise MetaPayloadError(f"{k} required")
    except KeyError as e:
        raise MetaPayloadError(f"missing key: {e}") from e
