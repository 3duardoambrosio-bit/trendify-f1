from __future__ import annotations

"""
Creative Pack Gate  enforcer numérico para evitar creativos basura.

Hard rules (SENTRIA deck):
- >= 3 creativos
- 3 formatos: 1:1, 4:5, 9:16
- min lado corto >= 1080px (hard floor)
- peso <= 30MB (Meta Help Center)
- dHash distance >= 6 (anti-duplicados perceptuales)

Nota: requiere Pillow para leer píxeles y calcular dHash.
Si Pillow no está, el gate FAIL-CLOSED con error claro.

__MARKER__ embedded in module constant below.
"""

import logging
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__MARKER__ = "SESSION_S12_creative_pack_gate_2026-03-02"

log = logging.getLogger(__name__)

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class CreativeGateConfig:
    min_total: int = 3
    min_short_side_px: int = 1080
    max_bytes: int = 30 * 1024 * 1024
    min_dhash_distance: int = 6


@dataclass(frozen=True)
class CreativeGateResult:
    allowed: bool
    errors: List[str]
    warnings: List[str]
    total_files: int
    buckets: Dict[str, int]


def _import_pillow():
    try:
        from PIL import Image  # type: ignore
        return Image
    except Exception:
        return None


def _bucket_ratio(w: int, h: int) -> str:
    # tolerant bucketing around canonical ratios
    if h <= 0 or w <= 0:
        return "other"
    r = w / h

    def close(a: float, b: float, tol: float = 0.06) -> bool:
        return abs(a - b) <= tol

    if close(r, 1.0):
        return "1:1"
    if close(r, 4 / 5):
        return "4:5"
    if close(r, 9 / 16):
        return "9:16"
    return "other"


def _dhash_64(img) -> int:
    # dHash 8x8 -> 64-bit int
    img = img.convert("L").resize((9, 8))
    px = list(img.getdata())
    bits = 0
    for row in range(8):
        base = row * 9
        for col in range(8):
            left = px[base + col]
            right = px[base + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def validate_kit_dir(kit_path: str, cfg: Optional[CreativeGateConfig] = None) -> CreativeGateResult:
    cfg = cfg or CreativeGateConfig()
    root = Path(kit_path)

    errors: List[str] = []
    warnings: List[str] = []

    if not root.exists() or not root.is_dir():
        return CreativeGateResult(False, ["kit_path_not_found"], [], 0, {"1:1": 0, "4:5": 0, "9:16": 0})

    files = sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS], key=lambda x: x.name)
    total = len(files)

    buckets = {"1:1": 0, "4:5": 0, "9:16": 0}

    if total < cfg.min_total:
        errors.append(f"min_total_failed:got={total}:need={cfg.min_total}")
        return CreativeGateResult(False, errors, warnings, total, buckets)

    Image = _import_pillow()
    if Image is None:
        errors.append("pillow_missing:install_pillow_to_enable_dhash_and_dimensions")
        return CreativeGateResult(False, errors, warnings, total, buckets)

    dhs: List[Tuple[Path, int]] = []

    for p in files:
        sz = p.stat().st_size
        if sz > cfg.max_bytes:
            errors.append(f"max_bytes_failed:file={p.name}:bytes={sz}:limit={cfg.max_bytes}")
            return CreativeGateResult(False, errors, warnings, total, buckets)

        with Image.open(p) as im:
            w, h = im.size
            if min(w, h) < cfg.min_short_side_px:
                errors.append(f"min_resolution_failed:file={p.name}:w={w}:h={h}:min_short={cfg.min_short_side_px}")
                return CreativeGateResult(False, errors, warnings, total, buckets)

            b = _bucket_ratio(w, h)
            if b in buckets:
                buckets[b] += 1

            dhs.append((p, _dhash_64(im)))

    # format coverage
    missing = [k for k, v in buckets.items() if v < 1]
    if missing:
        errors.append(f"format_coverage_failed:missing={','.join(missing)}:buckets={buckets}")
        return CreativeGateResult(False, errors, warnings, total, buckets)

    # duplicate detection
    for i in range(len(dhs)):
        for j in range(i + 1, len(dhs)):
            d = _hamming(dhs[i][1], dhs[j][1])
            if d < cfg.min_dhash_distance:
                errors.append(f"duplicate_failed:dhash_distance={d}:min={cfg.min_dhash_distance}:a={dhs[i][0].name}:b={dhs[j][0].name}")
                return CreativeGateResult(False, errors, warnings, total, buckets)

    return CreativeGateResult(True, [], warnings, total, buckets)
