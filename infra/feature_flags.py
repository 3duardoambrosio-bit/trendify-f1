"""Compatibility facade for canonical feature flags."""

from __future__ import annotations

from config.feature_flags import (
    FeatureFlags,
    _env_first,
    _normalize,
    _parse_bool,
)

__all__ = [
    "FeatureFlags",
    "_env_first",
    "_normalize",
    "_parse_bool",
]
