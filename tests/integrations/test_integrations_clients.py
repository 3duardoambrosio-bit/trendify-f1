from __future__ import annotations

from synapse.integrations.clients import (
    build_dropi_client,
    build_meta_client,
    build_shopify_client,
)


def test_clients_import_and_health() -> None:
    s = build_shopify_client()
    d = build_dropi_client()
    m = build_meta_client()

    hs = s.health()
    hd = d.health()
    hm = m.health()

    assert hs["ok"] is False
    assert hd["ok"] is False
    assert hm["ok"] is False

    assert hs["client"] == "shopify"
    assert hd["client"] == "dropi"
    assert hm["client"] == "meta"