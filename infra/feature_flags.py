from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict


def _parse_bool(raw: str, *, default: bool) -> bool:
    v = (raw or "").strip().lower()
    if v == "":
        return default
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class FeatureFlags:
    """
    Feature flags por ENV, FAIL-CLOSED por default.

    Reglas:
    - dry_run default True (seguro).
    - live_* defaults False (no tocar redes reales por accidente).
    """
    dry_run: bool = True
    live_meta: bool = False
    live_shopify: bool = False
    live_dropi: bool = False

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        return cls(
            dry_run=_parse_bool(os.getenv("SYNAPSE_DRY_RUN", ""), default=True),
            live_meta=_parse_bool(os.getenv("SYNAPSE_LIVE_META", ""), default=False),
            live_shopify=_parse_bool(os.getenv("SYNAPSE_LIVE_SHOPIFY", ""), default=False),
            live_dropi=_parse_bool(os.getenv("SYNAPSE_LIVE_DROPI", ""), default=False),
        )

    def as_dict(self) -> Dict[str, bool]:
        return {
            "dry_run": self.dry_run,
            "live_meta": self.live_meta,
            "live_shopify": self.live_shopify,
            "live_dropi": self.live_dropi,
        }

    def allow_network(self, system: str) -> bool:
        s = (system or "").strip().lower()
        if self.dry_run:
            return False
        if s == "meta":
            return self.live_meta
        if s == "shopify":
            return self.live_shopify
        if s == "dropi":
            return self.live_dropi
        return False