"""PipelineE2E keeps operator alerts outside its fail-closed boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from synapse.meta.account_health import (
    AccountHealthChecker,
    AccountHealthConfig,
    AccountMetrics,
)
from synapse.meta.advantage_plus import (
    AdvantagePlusCampaignBuilder,
    AdvantagePlusConfig,
)
from synapse.meta.pipeline_e2e import (
    PUBLISH_NOT_CONNECTED,
    PipelineE2E,
    PipelineE2EConfig,
)
from synapse.meta.warm_up_protocol import WarmUpConfig, WarmUpProtocol


@dataclass
class FakeProduct:
    sku: str
    creatives: list[dict]
    pixel_events: list[str]

    @property
    def product(self):
        return self


def test_pipeline_alert_transport_is_not_wired() -> None:
    """Operator notification belongs to a future governed orchestrator."""
    source = Path("synapse/meta/pipeline_e2e.py").read_text(encoding="utf-8")

    assert "get_alert_sink" not in source
    assert "TelegramAlertSink" not in source
    assert "SimpleHttpClient" not in source


def test_blocked_publish_makes_zero_alert_or_publisher_calls() -> None:
    """The local pipeline returns a fixed block without any external surface."""
    create_campaign = Mock(
        side_effect=AssertionError("create_campaign must not be called")
    )
    create_campaign_safe = Mock(
        side_effect=AssertionError("create_campaign_safe must not be called")
    )
    publisher = SimpleNamespace(
        create_campaign=create_campaign,
        create_campaign_safe=create_campaign_safe,
    )
    alert_factory = Mock(
        side_effect=AssertionError("alert sink must not be accessed")
    )

    with patch(
        "synapse.infra.alert_wiring.get_alert_sink",
        alert_factory,
    ):
        pipeline = PipelineE2E(
            safe_client=publisher,
            health_checker=AccountHealthChecker(AccountHealthConfig()),
            warm_up=WarmUpProtocol(
                WarmUpConfig(),
                datetime.now(timezone.utc) - timedelta(days=20),
            ),
            advantage_plus=AdvantagePlusCampaignBuilder(
                AdvantagePlusConfig()
            ),
            config=PipelineE2EConfig(
                enable_publish=True,
                enable_creative_gate=False,
                default_budget_daily_usd=Decimal("10"),
                daily_cap_usd=Decimal("50"),
            ),
        )
        result = pipeline.execute(
            products=[
                FakeProduct(
                    sku="SKU-BLOCKED",
                    creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
                    pixel_events=["Purchase"],
                )
            ],
            account_metrics=AccountMetrics(
                ad_disapproval_rate=0.01,
                spend_velocity_ratio=1.0,
                account_age_days=20,
                has_policy_violation=False,
            ),
        )

    assert result.rc == 2
    assert result.diagnostic == PUBLISH_NOT_CONNECTED
    assert result.products_processed == 1
    assert result.campaigns_created == 0
    assert result.campaigns_blocked == 1
    assert result.errors == [
        {
            "stage": "publish",
            "product": "SKU-BLOCKED",
            "error": PUBLISH_NOT_CONNECTED,
        }
    ]
    assert result.external_write is False
    assert result.publish_connected is False
    assert result.live_api_enabled is False
    alert_factory.assert_not_called()
    create_campaign.assert_not_called()
    create_campaign_safe.assert_not_called()
