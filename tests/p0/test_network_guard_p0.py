from __future__ import annotations

import pytest

from infra.network_guard import classify_system, decide_url, enforce_url_policy


def test_classify_system_domains():
    assert classify_system("https://graph.facebook.com/v20.0/me") == "meta"
    assert classify_system("https://api.dropi.co/orders") == "dropi"
    assert classify_system("https://foo.myshopify.com/admin") == "shopify"
    assert classify_system("https://example.com") is None


def test_default_blocks_sensitive(monkeypatch):
    # Defaults fail-closed: dry_run True -> no network to sensitive domains.
    monkeypatch.delenv("SYNAPSE_DRY_RUN", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_DROPI", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_SHOPIFY", raising=False)

    d = decide_url("https://graph.facebook.com/v20.0/me")
    assert d.allowed is False
    assert d.system == "meta"
    assert "NETWORK_BLOCKED_BY_FLAGS" in (d.reason or "")

    with pytest.raises(RuntimeError) as ex:
        enforce_url_policy("https://api.dropi.co/orders")
    assert "NETWORK_BLOCKED_BY_FLAGS" in str(ex.value)


def test_live_requires_two_switches(monkeypatch):
    # live_meta=1 pero dry_run=1 => sigue bloqueado
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    d1 = decide_url("https://graph.facebook.com/v20.0/me")
    assert d1.allowed is False

    # dry_run=0 + live_meta=1 => permitido
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    d2 = decide_url("https://graph.facebook.com/v20.0/me")
    assert d2.allowed is True