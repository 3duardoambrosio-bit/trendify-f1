# V3GAP:optimization_event_ladder

# V3GAP:B-05_advantage_plus_2025

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from synapse.meta.advantage_plus import AdvantagePlusCampaignBuilder, AdvantagePlusConfig


@dataclass
class DummyProduct:
    sku: str
    pixel_events: list[str]


def test_valid_prerequisites_pass() -> None:
    b = AdvantagePlusCampaignBuilder(AdvantagePlusConfig())
    ok, errs = b.validate_prerequisites(creatives_count=5, pixel_events=["Purchase"], budget_daily=Decimal("10"))
    assert ok is True
    assert errs == []


def test_insufficient_creatives_blocks() -> None:
    b = AdvantagePlusCampaignBuilder(AdvantagePlusConfig())
    ok, errs = b.validate_prerequisites(creatives_count=1, pixel_events=["Purchase"], budget_daily=Decimal("10"))
    assert ok is False
    assert "insufficient_creatives(<3)" in errs


def test_payload_has_required_fields() -> None:
    b = AdvantagePlusCampaignBuilder(AdvantagePlusConfig())
    p = DummyProduct(sku="SKU-1", pixel_events=["Purchase"])
    payload = b.build_campaign_payload(product=p, budget_daily=Decimal("10"), creatives=[{"id": 1}, {"id": 2}, {"id": 3}])
    assert "campaign_objective" in payload
    assert "optimization_goal" in payload