from __future__ import annotations

from pathlib import Path

from synapse.marketing_os.exporters.shopify_pack import write_shopify_products_csv


def test_shopify_csv_utf8_no_bom_and_lf(tmp_path: Path) -> None:
    out = write_shopify_products_csv(tmp_path, product={"title": "Cámara Pro", "description": "Desc"})
    raw = out.read_bytes()

    # NO BOM
    assert not raw.startswith(b"\xef\xbb\xbf")

    # UTF-8 decodable
    txt = raw.decode("utf-8")
    assert "Cámara Pro" in txt

    # LF only
    assert "\r\n" not in txt
    assert "\r" not in txt

    # basic shape
    assert txt.startswith("Handle,Title,Body (HTML),Vendor,Tags,Status\n")
    assert "camara-pro" in txt
