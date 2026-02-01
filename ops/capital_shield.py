# DEPRECATED: Use ops.capital_shield_v2 for new code.
# This module re-exports the v1 implementation for backwards compatibility.
# It will be removed in a future version.
from __future__ import annotations

import warnings

warnings.warn(
    "ops.capital_shield is deprecated. Use ops.capital_shield_v2 instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export v1 classes for backwards compatibility
from ops.capital_shield_v1_DEPRECATED import (  # noqa: F401
    CapitalShield,
    CapitalShieldConfig,
    SpendDecision,
)
