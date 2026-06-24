from __future__ import annotations

import pytest

import ops.dropi_client as dropi_client


def _client() -> dropi_client.DropiClient:
    cfg = dropi_client.DropiClientConfig(
        base_url="https://api.dropi.co/integrations",
        integration_key="test-key",
        timeout_s=1,
        rate_limit_s=0,
    )
    return dropi_client.DropiClient(cfg)


def _bomb_urlopen(*_args, **_kwargs):
    raise AssertionError("urlopen must not be reached while Dropi guard is closed")


def test_dropi_get_is_blocked_by_default_before_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_DROPI", "0")
    monkeypatch.setattr(dropi_client.urllib.request, "urlopen", _bomb_urlopen)

    with pytest.raises(RuntimeError, match="SYNAPSE_LIVE_DROPI"):
        _client().get("/products/index")


def test_dropi_readonly_post_is_blocked_by_default_before_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_DROPI", "0")
    monkeypatch.setattr(dropi_client.urllib.request, "urlopen", _bomb_urlopen)

    with pytest.raises(RuntimeError, match="SYNAPSE_LIVE_DROPI"):
        _client().post_readonly("/products/index", {"pageSize": 1})


def test_dropi_readonly_post_rejects_non_allowlisted_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")
    monkeypatch.setenv("SYNAPSE_LIVE_DROPI", "1")
    monkeypatch.setattr(dropi_client.urllib.request, "urlopen", _bomb_urlopen)

    with pytest.raises(RuntimeError, match="not allowlisted"):
        _client().post_readonly("/orders/create", {"id": "unsafe"})


def test_dropi_generic_post_requires_live_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")
    monkeypatch.setenv("SYNAPSE_LIVE_DROPI", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_WRITE", "0")
    monkeypatch.setattr(dropi_client.urllib.request, "urlopen", _bomb_urlopen)

    with pytest.raises(RuntimeError, match="SYNAPSE_LIVE_WRITE"):
        _client().post("/orders/create", {"id": "unsafe"})


def test_dropi_generic_post_requires_explicit_write_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")
    monkeypatch.setenv("SYNAPSE_LIVE_DROPI", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_WRITE", "1")
    monkeypatch.delenv("SYNAPSE_DROPI_WRITE_APPROVED", raising=False)
    monkeypatch.setattr(dropi_client.urllib.request, "urlopen", _bomb_urlopen)

    with pytest.raises(RuntimeError, match="SYNAPSE_DROPI_WRITE_APPROVED"):
        _client().post("/orders/create", {"id": "unsafe"})


def test_dropi_product_finder_uses_readonly_post_transport() -> None:
    source = open("ops/dropi_product_finder.py", encoding="utf-8").read()
    assert 'client.post_readonly("/products/index", body)' in source
    assert 'client.post("/products/index", body)' not in source
