from __future__ import annotations

import types

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
