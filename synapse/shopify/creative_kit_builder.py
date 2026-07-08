from __future__ import annotations

"""
Creative Kit Builder — S12.2

Genera un kit mínimo Advantage+ desde 1 imagen fuente:
- 1:1  (1080x1080)
- 4:5  (1080x1350)
- 9:16 (1080x1920)

Estrategia: resize-to-cover + center-crop (sin letterbox).
Salida: JPEG (control de peso). Si excede max_bytes, baja calidad hasta cumplir o falla.

__MARKER__ embedded in module constant below.
"""

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import deal

__MARKER__ = "SESSION_S12_2_creative_kit_builder_2026-03-02"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreativeKitBuilderConfig:
    max_bytes: int = 30 * 1024 * 1024
    min_quality: int = 55
    start_quality: int = 90
    quality_step: int = 5
    targets: Tuple[Tuple[str, int, int], ...] = (
        ("a_1x1.jpg", 1080, 1080),
        ("b_4x5.jpg", 1080, 1350),
        ("c_9x16.jpg", 1080, 1920),
    )


@dataclass(frozen=True)
class CreativeKitBuildResult:
    success: bool
    out_dir: str
    files: List[str]
    errors: List[str]
    warnings: List[str]


def _import_pillow():
    try:
        from PIL import Image  # type: ignore
        return Image
    except Exception:
        return None


def _best_lanczos(Image):
    # Pillow compat: Resampling enum exists on module, not on image instance.
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    # Older fallback
    if hasattr(Image, "LANCZOS"):
        return Image.LANCZOS
    # Last resort (legacy)
    return Image.ANTIALIAS


def _cover_crop(im, tw: int, th: int, resample_filter):
    w, h = im.size
    if w <= 0 or h <= 0:
        raise ValueError("invalid_image_dimensions")

    scale = max(tw / w, th / h)
    nw = int(round(w * scale))
    nh = int(round(h * scale))

    im2 = im.resize((nw, nh), resample=resample_filter)

    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    right = left + tw
    bottom = top + th
    return im2.crop((left, top, right, bottom))


def _encode_jpeg_under_limit(img, max_bytes: int, start_q: int, min_q: int, step: int) -> Tuple[bytes, int]:
    q = start_q
    last: Optional[bytes] = None
    last_q = q

    if img.mode != "RGB":
        img = img.convert("RGB")

    while q >= min_q:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        data = buf.getvalue()
        last = data
        last_q = q
        if len(data) <= max_bytes:
            return data, q
        q -= step

    raise ValueError(f"jpeg_over_limit bytes={len(last) if last else -1} last_q={last_q} max_bytes={max_bytes}")


@deal.pre(lambda input_path, out_dir, cfg=None: isinstance(input_path, str) and input_path.strip() != "")
@deal.pre(lambda input_path, out_dir, cfg=None: isinstance(out_dir, str) and out_dir.strip() != "")
@deal.post(lambda result: isinstance(result, CreativeKitBuildResult))
def build_creative_kit(input_path: str, out_dir: str, cfg: Optional[CreativeKitBuilderConfig] = None) -> CreativeKitBuildResult:
    cfg = cfg or CreativeKitBuilderConfig()
    errors: List[str] = []
    warnings: List[str] = []
    files: List[str] = []

    Image = _import_pillow()
    if Image is None:
        return CreativeKitBuildResult(False, out_dir, [], ["pillow_missing"], [])

    src = Path(input_path)
    if not src.exists() or not src.is_file():
        return CreativeKitBuildResult(False, out_dir, [], ["input_not_found"], [])

    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)

    try:
        resample_filter = _best_lanczos(Image)

        with Image.open(src) as im:
            im = im.convert("RGB")

            for name, tw, th in cfg.targets:
                out_img = _cover_crop(im, tw, th, resample_filter)
                try:
                    data, q = _encode_jpeg_under_limit(
                        out_img,
                        max_bytes=cfg.max_bytes,
                        start_q=cfg.start_quality,
                        min_q=cfg.min_quality,
                        step=cfg.quality_step,
                    )
                except Exception as e:
                    errors.append(f"encode_failed:{name}:{type(e).__name__}:{e}")
                    return CreativeKitBuildResult(False, str(od), files, errors, warnings)

                out_file = od / name
                out_file.write_bytes(data)
                files.append(str(out_file))

                if q < cfg.start_quality:
                    warnings.append(f"quality_reduced:{name}:q={q}")

    except Exception as e:
        errors.append(f"build_failed:{type(e).__name__}:{e}")
        return CreativeKitBuildResult(False, str(od), files, errors, warnings)

    return CreativeKitBuildResult(True, str(od), files, errors, warnings)
