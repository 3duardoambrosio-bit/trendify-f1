from __future__ import annotations

from pathlib import Path

import pytest

from synapse.shopify.creative_pack_gate import CreativeGateConfig, validate_kit_dir


def _mkimg(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    Image = pytest.importorskip("PIL.Image")
    img = Image.new("RGB", size, color=color)
    img.save(path)


def test_gate_pass_with_3_formats(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080)
    _mkimg(tmp_path / "a_1x1.png", (1080, 1080), (255, 0, 0))
    _mkimg(tmp_path / "b_4x5.png", (1080, 1350), (0, 255, 0))
    _mkimg(tmp_path / "c_9x16.png", (1080, 1920), (0, 0, 255))

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is True
    assert r.errors == []
    assert r.buckets["1:1"] >= 1
    assert r.buckets["4:5"] >= 1
    assert r.buckets["9:16"] >= 1


def test_gate_fails_missing_format(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080)
    _mkimg(tmp_path / "a_1x1.png", (1080, 1080), (255, 0, 0))
    _mkimg(tmp_path / "b_1x1.png", (1080, 1080), (0, 255, 0))
    _mkimg(tmp_path / "c_1x1.png", (1080, 1080), (0, 0, 255))

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is False
    assert any("format_coverage_failed" in e for e in r.errors)


def test_gate_fails_low_resolution(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080)
    _mkimg(tmp_path / "a_1x1.png", (800, 800), (255, 0, 0))
    _mkimg(tmp_path / "b_4x5.png", (1080, 1350), (0, 255, 0))
    _mkimg(tmp_path / "c_9x16.png", (1080, 1920), (0, 0, 255))

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is False
    assert any("min_resolution_failed" in e for e in r.errors)


def test_gate_fails_duplicates(tmp_path: Path):
    cfg = CreativeGateConfig(min_total=3, min_short_side_px=1080, min_dhash_distance=6)
    # two identical images => dHash distance 0
    _mkimg(tmp_path / "a_1x1.png", (1080, 1080), (10, 10, 10))
    _mkimg(tmp_path / "b_4x5.png", (1080, 1350), (10, 10, 10))
    _mkimg(tmp_path / "c_9x16.png", (1080, 1920), (0, 0, 255))

    r = validate_kit_dir(str(tmp_path), cfg)
    assert r.allowed is False
    assert any("duplicate_failed" in e for e in r.errors)
