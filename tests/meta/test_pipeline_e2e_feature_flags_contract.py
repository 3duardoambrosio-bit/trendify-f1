from __future__ import annotations

import types
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import synapse.meta.pipeline_e2e as pe


class _Flags:
    def __init__(self, value: bool):
        self.value = value
        self.calls = []

    def is_on(self, name: str, default: bool = False) -> bool:
        self.calls.append((name, default))
        return self.value


def test_flag_enabled_delegates_to_synapse_infra_feature_flags(monkeypatch):
    flags = _Flags(True)

    class _FeatureFlags:
        @staticmethod
        def load():
            return flags

    monkeypatch.setattr(pe, "_feature_flags", types.SimpleNamespace(FeatureFlags=_FeatureFlags))
    monkeypatch.delenv("SYNAPSE_FLAG_META_LIVE_API", raising=False)
    monkeypatch.delenv("meta_live_api", raising=False)

    assert pe._flag_enabled("meta_live_api") is True
    assert flags.calls == [("meta_live_api", False)]


def test_flag_enabled_prefers_prefixed_env_fallback(monkeypatch):
    class _BrokenFeatureFlags:
        @staticmethod
        def load():
            raise RuntimeError("boom")

    monkeypatch.setattr(pe, "_feature_flags", types.SimpleNamespace(FeatureFlags=_BrokenFeatureFlags))
    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "1")
    monkeypatch.delenv("meta_live_api", raising=False)

    assert pe._flag_enabled("meta_live_api") is True

    monkeypatch.setenv("SYNAPSE_FLAG_META_LIVE_API", "0")
    assert pe._flag_enabled("meta_live_api") is False


def test_flag_enabled_legacy_raw_env_still_works(monkeypatch):
    monkeypatch.setattr(pe, "_feature_flags", types.SimpleNamespace())
    monkeypatch.delenv("SYNAPSE_FLAG_META_LIVE_API", raising=False)
    monkeypatch.setenv("meta_live_api", "true")

    assert pe._flag_enabled("meta_live_api") is True


def test_enabled_live_flag_never_connects_pipeline_publishing(monkeypatch):
    from synapse.meta.account_health import (
        AccountHealthChecker,
        AccountHealthConfig,
        AccountMetrics,
    )
    from synapse.meta.advantage_plus import (
        AdvantagePlusCampaignBuilder,
        AdvantagePlusConfig,
    )
    from synapse.meta.warm_up_protocol import WarmUpConfig, WarmUpProtocol

    flags = _Flags(True)

    class _FeatureFlags:
        @staticmethod
        def load():
            return flags

    @dataclass
    class _Product:
        sku: str
        creatives: list[dict]
        pixel_events: list[str]

        @property
        def product(self):
            return self

    create_campaign = Mock(
        side_effect=AssertionError("legacy publisher must not be called")
    )
    create_campaign_safe = Mock(
        side_effect=AssertionError("safe publisher must not be called")
    )
    publisher = types.SimpleNamespace(
        create_campaign=create_campaign,
        create_campaign_safe=create_campaign_safe,
    )
    monkeypatch.setattr(
        pe,
        "_feature_flags",
        types.SimpleNamespace(FeatureFlags=_FeatureFlags),
    )

    pipeline = pe.PipelineE2E(
        safe_client=publisher,
        health_checker=AccountHealthChecker(AccountHealthConfig()),
        warm_up=WarmUpProtocol(
            WarmUpConfig(),
            datetime.now(timezone.utc) - timedelta(days=20),
        ),
        advantage_plus=AdvantagePlusCampaignBuilder(AdvantagePlusConfig()),
        config=pe.PipelineE2EConfig(),
    )
    metrics = AccountMetrics(
        ad_disapproval_rate=0.01,
        spend_velocity_ratio=1.0,
        account_age_days=20,
        has_policy_violation=False,
    )

    out = pipeline.execute(
        products=[
            _Product(
                sku="SKU-1",
                creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
                pixel_events=["Purchase"],
            )
        ],
        account_metrics=metrics,
    )

    assert out.rc == 0
    assert out.campaigns_created == 0
    assert out.external_write is False
    assert out.publish_connected is False
    assert out.live_api_enabled is False
    create_campaign.assert_not_called()
    create_campaign_safe.assert_not_called()
