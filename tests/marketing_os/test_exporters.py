from __future__ import annotations

import json
from pathlib import Path

from synapse.marketing_os.exporters.meta_bundle import write_meta_bundle
from synapse.marketing_os.exporters.shopify_pack import write_shopify_products_csv


def test_meta_bundle_writes_json(tmp_path: Path) -> None:
    out = write_meta_bundle(tmp_path, product_id="p1", creatives=[{"primary_text": "x"}])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["product_id"] == "p1"
    assert payload["count"] == 1


def test_shopify_csv_utf8_sig(tmp_path: Path) -> None:
    out = write_shopify_products_csv(tmp_path, product={"title": "Cámara Pro", "description": "Desc"})
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8-SIG
    txt = out.read_text(encoding="utf-8-sig")
    assert "Handle,Title" in txt
    assert "C\u00e1mara Pro" in txt
