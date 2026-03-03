from __future__ import annotations

from pathlib import Path

import pytest

from synapse.shopify.creative_kit_builder import build_creative_kit
from synapse.shopify.creative_pack_gate import validate_kit_dir


def _mk_src(path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")

    img = Image.new("RGB", (2000, 1400), (240, 240, 240))
    d = ImageDraw.Draw(img)
    d.rectangle((50, 50, 650, 350), outline=(0, 0, 0), width=8)
    d.line((0, 0, 1999, 1399), fill=(0, 0, 0), width=6)
    img.save(path)


def test_build_creative_kit_generates_3_and_passes_gate(tmp_path: Path):
    src = tmp_path / "src.jpg"
    out_dir = tmp_path / "kit"

    _mk_src(src)
    r = build_creative_kit(str(src), str(out_dir))

    assert r.success is True
    assert r.errors == []
    assert len(r.files) == 3

    # Dimensions check via Pillow
    Image = pytest.importorskip("PIL.Image")
    dims = {}
    for f in r.files:
        with Image.open(f) as im:
            dims[Path(f).name] = im.size

    assert dims["a_1x1.jpg"] == (1080, 1080)
    assert dims["b_4x5.jpg"] == (1080, 1350)
    assert dims["c_9x16.jpg"] == (1080, 1920)

    g = validate_kit_dir(str(out_dir))
    assert g.allowed is True
    assert g.errors == []
