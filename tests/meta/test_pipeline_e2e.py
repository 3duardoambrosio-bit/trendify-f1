from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
class DummyProductScore:
    sku: str
    creatives: list[dict]
    pixel_events: list[str]

    @property
    def product(self):
        return self


class BombPublisher:
    def __init__(self):
        self.create_campaign_calls = 0
        self.create_campaign_safe_calls = 0
        self.other_calls = 0

    def create_campaign(self, payload: dict) -> dict:
        self.create_campaign_calls += 1
        raise AssertionError("legacy campaign publisher must not be called")

    def create_campaign_safe(self, *args, **kwargs) -> dict:
        self.create_campaign_safe_calls += 1
        raise AssertionError("MetaSafeClient adapter must not be called")

    def __getattr__(self, name: str):
        self.other_calls += 1
        raise AssertionError(f"unexpected publisher interface: {name}")


def _build_pipeline(
    *,
    enable_publish: bool = False,
    created_days_ago: int = 20,
    warm_config: WarmUpConfig | None = None,
    advantage_config: AdvantagePlusConfig | None = None,
) -> tuple[PipelineE2E, BombPublisher]:
    publisher = BombPublisher()
    health = AccountHealthChecker(AccountHealthConfig())
    created = datetime.now(timezone.utc) - timedelta(days=created_days_ago)
    warm = WarmUpProtocol(warm_config or WarmUpConfig(), created)
    advantage = AdvantagePlusCampaignBuilder(
        advantage_config or AdvantagePlusConfig()
    )
    config = PipelineE2EConfig(
        enable_publish=enable_publish,
        default_budget_daily_usd=Decimal("10"),
        daily_cap_usd=Decimal("50"),
    )
    return (
        PipelineE2E(
            safe_client=publisher,
            health_checker=health,
            warm_up=warm,
            advantage_plus=advantage,
            config=config,
        ),
        publisher,
    )


def _healthy_metrics(*, policy_violation: bool = False) -> AccountMetrics:
    return AccountMetrics(
        ad_disapproval_rate=0.01,
        spend_velocity_ratio=1.0,
        account_age_days=20,
        has_policy_violation=policy_violation,
    )


def _valid_product() -> DummyProductScore:
    return DummyProductScore(
        sku="SKU-1",
        creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
        pixel_events=["Purchase"],
    )


def _assert_no_publisher_calls(publisher: BombPublisher) -> None:
    assert publisher.create_campaign_calls == 0
    assert publisher.create_campaign_safe_calls == 0
    assert publisher.other_calls == 0


def test_pipeline_publish_is_disabled_by_default() -> None:
    assert PipelineE2EConfig().enable_publish is False


def test_e2e_red_health_blocks_all_without_publisher_calls(
    monkeypatch,
) -> None:
    import synapse.infra.alert_wiring as alert_wiring

    def bomb_alert(*args, **kwargs):
        raise AssertionError("health block must not access alert transports")

    monkeypatch.setattr(alert_wiring, "get_alert_sink", bomb_alert)
    pipeline, publisher = _build_pipeline(enable_publish=True)

    out = pipeline.execute(
        products=[_valid_product()],
        account_metrics=_healthy_metrics(policy_violation=True),
    )

    assert out.rc == 2
    assert out.diagnostic == PUBLISH_NOT_CONNECTED
    assert out.campaigns_created == 0
    assert out.campaigns_blocked == 1
    assert out.external_write is False
    assert out.publish_connected is False
    assert out.live_api_enabled is False
    _assert_no_publisher_calls(publisher)


def test_e2e_offline_happy_path_prepares_locally_without_publishing() -> None:
    pipeline, publisher = _build_pipeline()

    out = pipeline.execute(
        products=[_valid_product()],
        account_metrics=_healthy_metrics(),
    )

    assert out.rc == 0
    assert out.diagnostic == ""
    assert out.products_processed == 1
    assert out.campaigns_created == 0
    assert out.campaigns_blocked == 0
    assert out.errors == []
    assert out.external_write is False
    assert out.publish_connected is False
    assert out.live_api_enabled is False
    _assert_no_publisher_calls(publisher)


def test_e2e_explicit_publish_request_fails_closed_without_interfaces(
    monkeypatch,
) -> None:
    import synapse.infra.alert_wiring as alert_wiring

    def bomb_alert(*args, **kwargs):
        raise AssertionError("pipeline must not access alert transports")

    monkeypatch.setattr(alert_wiring, "get_alert_sink", bomb_alert)
    pipeline, publisher = _build_pipeline(enable_publish=True)

    out = pipeline.execute(
        products=[_valid_product()],
        account_metrics=_healthy_metrics(),
    )

    assert out.rc == 2
    assert out.diagnostic == PUBLISH_NOT_CONNECTED
    assert out.products_processed == 1
    assert out.campaigns_created == 0
    assert out.campaigns_blocked == 1
    assert out.external_write is False
    assert out.publish_connected is False
    assert out.live_api_enabled is False
    assert any(
        error.get("error") == PUBLISH_NOT_CONNECTED
        for error in out.errors
    )
    _assert_no_publisher_calls(publisher)


def test_e2e_warm_up_remains_functional_offline() -> None:
    pipeline, publisher = _build_pipeline(
        created_days_ago=1,
        warm_config=WarmUpConfig(
            initial_daily_usd=Decimal("5"),
            ramp_pct=Decimal("0.20"),
            min_account_age_days=10,
            ramp_start_day=3,
        ),
        advantage_config=AdvantagePlusConfig(
            min_budget_daily_usd=Decimal("5"),
        ),
    )

    out = pipeline.execute(
        products=[_valid_product()],
        account_metrics=_healthy_metrics(),
    )

    assert out.rc == 0
    assert out.products_processed == 1
    assert out.campaigns_created == 0
    assert out.campaigns_blocked == 0
    assert out.warm_up_limit == Decimal("5")
    _assert_no_publisher_calls(publisher)
