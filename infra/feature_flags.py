from __future__ import annotations

"""Compatibility shim for legacy infra.feature_flags imports."""

from config.feature_flags import FLAGS, FeatureFlags, _parse_bool

__all__ = ["FeatureFlags", "FLAGS", "_parse_bool"]
