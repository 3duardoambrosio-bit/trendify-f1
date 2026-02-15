"""Canonical thresholds for safe clients. S7+S8."""

from __future__ import annotations

from decimal import Decimal

# ── S7: Meta Safe Client ──────────────────────────────────────
# Spend caps (MXN)
DEFAULT_DAILY_SPEND_CAP_MXN = Decimal("100")
AUTOPAUSE_RATIO = Decimal("0.8")

# Meta API timeouts / retry / circuit breaker
META_TIMEOUT_S = 10
META_RETRIES = 3
META_CB_FAILURES = 5
META_CB_RESET_S = 30

# ── S8: Dropi Order Forwarding ────────────────────────────────
DROPI_RETRIES = 3
DROPI_RETRY_BASE_DELAY_S = 1.0
DROPI_RETRY_MAX_DELAY_S = 10.0
DROPI_CB_FAILURES = 5
DROPI_CB_RESET_S = 30
