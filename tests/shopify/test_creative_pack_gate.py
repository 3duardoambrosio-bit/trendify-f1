from __future__ import annotations

from pathlib import Path

import pytest

from synapse.shopify.creative_pack_gate import CreativeGateConfig, validate_kit_dir


def _mkimg(path: Path, size: tuple[int, int], variant: int) -> None:
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")

    # White background + black pattern => stable dHash differences
    img = Image.new("RGB", size, color=(255, 255, 255))
    d = ImageDraw.Draw(img)

    w, h = size

    if variant == 1:
        # Diagonal + top-left block
        d.line((0, 0, w - 1, h - 1), fill=(0, 0, 0), width=max(1, w // 200))
        d.rectangle((0, 0, w // 6, h // 6), outline=(0, 0, 0), width=max(1, w // 300))
    elif variant == 2:
        # Opposite diagonal + bottom-right block
        d.line((0, h - 1, w - 1, 0), fill=(0, 0, 0), width=max(1, w // 200))
        d.rectangle((w - w // 6, h - h // 6, w - 1, h - 1), outline=(0, 0, 0), width=max(1, w // 300))
    elif variant == 3:
        # Cross + center box
        d.line((w // 2, 0, w // 2, h - 1), fill=(0, 0, 0), width=max(1, w // 220))
        d.line((0, h // 2, w - 1, h // 2), fill=(0, 0, 0), width=max(1, w // 220))
        d.rectangle((w // 3, h // 3, w * 2 // 3, h * 2 // 3), outline=(0, 0, 0), width=max(1, w // 320))
    else:
        # fallback: a small asymmetric dot
        d.rectangle((w // 10, h // 7, w // 10 + 10, h // 7 + 10), fill=(0, 0, 0))

    img.save(path)


def test_gate_pass_with_3_formats(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080, min_dhash_distance=6)

    _mkimg(tmp_path / "a_1x1.png", (1080, 1080), 1)
    _mkimg(tmp_path / "b_4x5.png", (1080, 1350), 2)
    _mkimg(tmp_path / "c_9x16.png", (1080, 1920), 3)

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is True
    assert r.errors == []
    assert r.buckets["1:1"] >= 1
    assert r.buckets["4:5"] >= 1
    assert r.buckets["9:16"] >= 1


def test_gate_fails_missing_format(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080)
    _mkimg(tmp_path / "a_1x1.png", (1080, 1080), 1)
    _mkimg(tmp_path / "b_1x1.png", (1080, 1080), 2)
    _mkimg(tmp_path / "c_1x1.png", (1080, 1080), 3)

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is False
    assert any("format_coverage_failed" in e for e in r.errors)


def test_gate_fails_low_resolution(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080)
    _mkimg(tmp_path / "a_1x1.png", (800, 800), 1)
    _mkimg(tmp_path / "b_4x5.png", (1080, 1350), 2)
    _mkimg(tmp_path / "c_9x16.png", (1080, 1920), 3)

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is False
    assert any("min_resolution_failed" in e for e in r.errors)


def test_gate_fails_duplicates(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080, min_dhash_distance=6)
    # identical pattern for first two => dHash distance ~0, should fail
    _mkimg(tmp_path / "a_1x1.png", (1080, 1080), 1)
    _mkimg(tmp_path / "b_4x5.png", (1080, 1350), 1)
    _mkimg(tmp_path / "c_9x16.png", (1080, 1920), 3)

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is False
    assert any("duplicate_failed" in e for e in r.errors)
