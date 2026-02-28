from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from synapse.meta.account_health import AccountHealthChecker, AccountHealthConfig, AccountMetrics
from synapse.meta.advantage_plus import AdvantagePlusCampaignBuilder, AdvantagePlusConfig
from synapse.meta.pipeline_e2e import PipelineE2E, PipelineE2EConfig
from synapse.meta.warm_up_protocol import WarmUpProtocol, WarmUpConfig


@dataclass
class DummyProductScore:
    sku: str
    creatives: list[dict]
    pixel_events: list[str]

    @property
    def product(self):
        return self


class FakeSafeClient:
    def __init__(self):
        self.payloads: list[dict] = []

    def create_campaign(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {"id": "CAMP-1"}


def test_e2e_red_health_blocks_all() -> None:
    safe = FakeSafeClient()
    health = AccountHealthChecker(AccountHealthConfig())
    created = datetime.now(timezone.utc) - timedelta(days=20)
    warm = WarmUpProtocol(WarmUpConfig(), created)
    ap = AdvantagePlusCampaignBuilder(AdvantagePlusConfig())
    cfg = PipelineE2EConfig(enable_publish=True)

    e2e = PipelineE2E(safe_client=safe, health_checker=health, warm_up=warm, advantage_plus=ap, config=cfg)

    metrics = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=1.0, account_age_days=20, has_policy_violation=True)
    products = [DummyProductScore(sku="SKU-1", creatives=[{"id": 1}, {"id": 2}, {"id": 3}], pixel_events=["Purchase"])]

    out = e2e.execute(products=products, account_metrics=metrics)
    assert out.campaigns_created == 0
    assert out.campaigns_blocked == 1


def test_e2e_happy_path_with_mock() -> None:
    safe = FakeSafeClient()
    health = AccountHealthChecker(AccountHealthConfig())
    created = datetime.now(timezone.utc) - timedelta(days=20)
    warm = WarmUpProtocol(WarmUpConfig(), created)
    ap = AdvantagePlusCampaignBuilder(AdvantagePlusConfig())
    cfg = PipelineE2EConfig(enable_publish=True, default_budget_daily_usd=Decimal("10"), daily_cap_usd=Decimal("50"))

    e2e = PipelineE2E(safe_client=safe, health_checker=health, warm_up=warm, advantage_plus=ap, config=cfg)

    metrics = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=1.0, account_age_days=20, has_policy_violation=False)
    products = [DummyProductScore(sku="SKU-1", creatives=[{"id": 1}, {"id": 2}, {"id": 3}], pixel_events=["Purchase"])]

    out = e2e.execute(products=products, account_metrics=metrics)
    assert out.campaigns_created > 0
    assert len(safe.payloads) == 1


def test_e2e_warm_up_adjusts_budget() -> None:
    safe = FakeSafeClient()
    health = AccountHealthChecker(AccountHealthConfig())
    created = datetime.now(timezone.utc) - timedelta(days=1)  # age 1 => warm-up
    warm = WarmUpProtocol(WarmUpConfig(initial_daily_usd=Decimal("5"), ramp_pct=Decimal("0.20"), min_account_age_days=10, ramp_start_day=3), created)
    ap = AdvantagePlusCampaignBuilder(AdvantagePlusConfig(min_budget_daily_usd=Decimal("5")))
    cfg = PipelineE2EConfig(enable_publish=True, default_budget_daily_usd=Decimal("10"), daily_cap_usd=Decimal("50"))

    e2e = PipelineE2E(safe_client=safe, health_checker=health, warm_up=warm, advantage_plus=ap, config=cfg)

    metrics = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=1.0, account_age_days=1, has_policy_violation=False)
    products = [DummyProductScore(sku="SKU-1", creatives=[{"id": 1}, {"id": 2}, {"id": 3}], pixel_events=["Purchase"])]

    out = e2e.execute(products=products, account_metrics=metrics)
    assert out.campaigns_created == 1
    assert safe.payloads[0]["budget_daily_usd"] == "5.00"