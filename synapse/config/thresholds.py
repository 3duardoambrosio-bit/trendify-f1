"""Canonical thresholds for Meta Safe Client. S7: meta safe client."""

from __future__ import annotations

from decimal import Decimal

# Spend caps (MXN)
DEFAULT_DAILY_SPEND_CAP_MXN = Decimal("100")
AUTOPAUSE_RATIO = Decimal("0.8")

# Meta API timeouts / retry / circuit breaker
META_TIMEOUT_S = 10
META_RETRIES = 3
META_CB_FAILURES = 5
META_CB_RESET_S = 30
