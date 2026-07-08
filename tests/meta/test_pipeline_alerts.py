"""S19 Tests: pipeline_e2e emits alert when campaigns are blocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from synapse.infra.alerts import NullAlertSink


def test_pipeline_alerts_grep_present():
    """Verify get_alert_sink is wired in pipeline_e2e source."""
    import pathlib
    src = pathlib.Path("synapse/meta/pipeline_e2e.py").read_text(encoding="utf-8")
    assert "get_alert_sink" in src, "pipeline_e2e must import get_alert_sink for S19 wiring"


def test_pipeline_alerts_on_blocked_campaigns():
    """When pipeline blocks campaigns, an alert should be emitted."""
    from dataclasses import dataclass
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from synapse.meta.account_health import AccountHealthChecker, AccountHealthConfig, AccountMetrics
    from synapse.meta.advantage_plus import AdvantagePlusCampaignBuilder, AdvantagePlusConfig
    from synapse.meta.pipeline_e2e import PipelineE2E, PipelineE2EConfig
    from synapse.meta.warm_up_protocol import WarmUpProtocol, WarmUpConfig

    @dataclass
    class FakeProduct:
        sku: str
        creatives: list
        pixel_events: list

        @property
        def product(self):
            return self

    class FakeSafeClient:
        def create_campaign(self, payload):
            return {"id": "CAMP-1"}

    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
        safe = FakeSafeClient()
        health = AccountHealthChecker(AccountHealthConfig())
        created = datetime.now(timezone.utc) - timedelta(days=20)
        warm = WarmUpProtocol(WarmUpConfig(), created)
        ap = AdvantagePlusCampaignBuilder(AdvantagePlusConfig())
        cfg = PipelineE2EConfig(
            enable_publish=True,
            enable_creative_gate=False,
            default_budget_daily_usd=Decimal("10"),
            daily_cap_usd=Decimal("50"),
        )
        e2e = PipelineE2E(safe_client=safe, health_checker=health, warm_up=warm, advantage_plus=ap, config=cfg)

        metrics = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=1.0, account_age_days=20, has_policy_violation=False)
        # Product with 0 creatives → advantage_plus prereq fails → blocked
        products = [FakeProduct(sku="SKU-FAIL", creatives=[], pixel_events=["Purchase"])]

        out = e2e.execute(products=products, account_metrics=metrics)

    assert out.campaigns_blocked == 1
    assert len(calls) >= 1
    assert "PIPELINE" in calls[0]
    assert "blocked" in calls[0].lower()
