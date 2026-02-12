from __future__ import annotations

from infra.feature_flags import FeatureFlags, _parse_bool


def test_parse_bool_contract():
    assert _parse_bool("1", default=False) is True
    assert _parse_bool("true", default=False) is True
    assert _parse_bool("0", default=True) is False
    assert _parse_bool("false", default=True) is False
    assert _parse_bool("???", default=True) is True
    assert _parse_bool("???", default=False) is False


def test_feature_flags_defaults_fail_closed(monkeypatch):
    monkeypatch.delenv("SYNAPSE_DRY_RUN", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_SHOPIFY", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_DROPI", raising=False)

    f = FeatureFlags.from_env()
    assert f.dry_run is True
    assert f.live_meta is False
    assert f.live_shopify is False
    assert f.live_dropi is False
    assert f.allow_network("meta") is False
    assert f.allow_network("shopify") is False
    assert f.allow_network("dropi") is False


def test_feature_flags_live_requires_two_switches(monkeypatch):
    # Aunque actives live_meta, si dry_run=True => NO network
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    f = FeatureFlags.from_env()
    assert f.dry_run is True
    assert f.live_meta is True
    assert f.allow_network("meta") is False

    # Ahora sí: dry_run=0 + live_meta=1 => network allowed
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    f2 = FeatureFlags.from_env()
    assert f2.dry_run is False
    assert f2.live_meta is True
    assert f2.allow_network("meta") is True