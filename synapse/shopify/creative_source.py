from __future__ import annotations

"""
Creative Source Registry — GAP-04.

Define fuentes de creativos para campañas:
- PRODUCT_IMAGE: imágenes de producto desde data de Shopify (payload ya obtenido por READ layer)
- WAVE_ASSET: assets locales generados por marketing_os wave
- MANUAL_UPLOAD: reservado (futuro)

Regla: Advantage+ requiere mínimo 3 creativos. Si no hay, regresamos lo que haya + warning (log).

__MARKER__ embedded in module constant below.
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

__MARKER__ = "SESSION_S11_creative_source_2026-03-02"

log = logging.getLogger(__name__)


class CreativeType(str, Enum):
    PRODUCT_IMAGE = "PRODUCT_IMAGE"
    WAVE_ASSET = "WAVE_ASSET"
    MANUAL_UPLOAD = "MANUAL_UPLOAD"


@dataclass(frozen=True)
class Creative:
    creative_id: str
    creative_type: CreativeType
    url: str
    width: Optional[int]
    height: Optional[int]
    format: str


class CreativeSource:
    def __init__(
        self,
        shopify_reader: Optional[Callable[[str], Dict]] = None,
        default_wave_kit_path: Optional[str] = None,
    ) -> None:
        self._shopify_reader = shopify_reader
        self._default_wave_kit_path = default_wave_kit_path

    def from_shopify_product(self, product_data: Dict) -> List[Creative]:
        imgs = _extract_images(product_data)
        creatives: List[Creative] = []
        for i, img in enumerate(imgs):
            url = _first_str(img, ["url", "src", "originalSrc", "transformedSrc"])
            if not url:
                continue
            w = _first_int(img, ["width"])
            h = _first_int(img, ["height"])
            fmt = _infer_format_from_url(url)
            creatives.append(
                Creative(
                    creative_id=f"shopify_img_{i}",
                    creative_type=CreativeType.PRODUCT_IMAGE,
                    url=url,
                    width=w,
                    height=h,
                    format=fmt,
                )
            )
        return creatives

    def from_wave_kit(self, kit_path: str) -> List[Creative]:
        p = Path(kit_path)
        if not p.exists() or not p.is_dir():
            log.warning("wave kit path missing: %s", kit_path)
            return []

        exts = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"}
        files = [x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in exts]
        creatives: List[Creative] = []
        for i, f in enumerate(sorted(files, key=lambda x: x.name)):
            url = f.as_posix()
            creatives.append(
                Creative(
                    creative_id=f"wave_{i}_{f.stem}",
                    creative_type=CreativeType.WAVE_ASSET,
                    url=url,
                    width=None,
                    height=None,
                    format=f.suffix.lower().lstrip("."),
                )
            )
        return creatives

    def get_creatives_for_product(self, product_id: str, sources: List[CreativeType]) -> List[Creative]:
        out: List[Creative] = []
        seen = set()

        for s in (sources or []):
            if s == CreativeType.PRODUCT_IMAGE:
                if self._shopify_reader is None:
                    log.warning("PRODUCT_IMAGE requested but shopify_reader is None; skipping")
                    continue
                data = self._shopify_reader(product_id)
                for c in self.from_shopify_product(data):
                    if c.url not in seen:
                        out.append(c)
                        seen.add(c.url)

            elif s == CreativeType.WAVE_ASSET:
                kit = self._default_wave_kit_path
                if not kit:
                    log.warning("WAVE_ASSET requested but default_wave_kit_path is None; skipping")
                    continue
                for c in self.from_wave_kit(kit):
                    if c.url not in seen:
                        out.append(c)
                        seen.add(c.url)

            elif s == CreativeType.MANUAL_UPLOAD:
                log.warning("MANUAL_UPLOAD not implemented in S11; skipping")
                continue

        if len(out) < 3:
            log.warning("Creative count < 3 (got=%s). Advantage+ may underperform.", len(out))

        return out


def _first_str(d: Dict, keys: List[str]) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _first_int(d: Dict, keys: List[str]) -> Optional[int]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, int):
            return v
    return None


def _infer_format_from_url(url: str) -> str:
    _, ext = os.path.splitext(url.lower())
    if ext.startswith("."):
        ext = ext[1:]
    return ext or "unknown"


def _extract_images(payload: Dict) -> List[Dict]:
    # tolera múltiples shapes: REST-like y GraphQL-like
    if not isinstance(payload, dict):
        return []

    # GraphQL common: payload["product"]["images"]["nodes"]
    product = payload.get("product")
    if isinstance(product, dict):
        images = product.get("images")
        if isinstance(images, dict):
            nodes = images.get("nodes")
            if isinstance(nodes, list):
                return [x for x in nodes if isinstance(x, dict)]
            edges = images.get("edges")
            if isinstance(edges, list):
                out = []
                for e in edges:
                    if isinstance(e, dict) and isinstance(e.get("node"), dict):
                        out.append(e["node"])
                return out
        if isinstance(images, list):
            return [x for x in images if isinstance(x, dict)]

    # REST-like: payload["images"] list
    images2 = payload.get("images")
    if isinstance(images2, list):
        return [x for x in images2 if isinstance(x, dict)]
    if isinstance(images2, dict):
        nodes = images2.get("nodes")
        if isinstance(nodes, list):
            return [x for x in nodes if isinstance(x, dict)]

    return []
