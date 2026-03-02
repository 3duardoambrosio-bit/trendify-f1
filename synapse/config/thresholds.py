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

# === SESSION S10: META WARM-UP + ACCOUNT HEALTH + ADVANTAGE+ ===
from decimal import Decimal

# Warm-up protocol
WARMUP_INITIAL_DAILY_USD = Decimal("5")
WARMUP_RAMP_PCT = Decimal("0.20")
WARMUP_MIN_ACCOUNT_AGE_DAYS = 10
WARMUP_RAMP_START_DAY = 3

# Account health
HEALTH_DISAPPROVAL_YELLOW = Decimal("0.10")
HEALTH_DISAPPROVAL_RED = Decimal("0.20")
HEALTH_VELOCITY_YELLOW = Decimal("3.0")

# Advantage+
ADVANTAGE_PLUS_MIN_CREATIVES = 3
ADVANTAGE_PLUS_LEARNING_DAYS = 7
ADVANTAGE_PLUS_MIN_DAILY_USD = Decimal("5")
# === SESSION S11: SHOPIFY WRITE + OXXO + CHECKOUT MX + COD ===

# OXXO limits
OXXO_MAX_AMOUNT_MXN = Decimal("10000")
OXXO_MIN_AMOUNT_MXN = Decimal("20")
OXXO_EXPIRY_HOURS = 72
OXXO_REMINDER_HOURS = 48

# COD risk
COD_MAX_AMOUNT_MXN = Decimal("2000")
COD_HIGH_RISK_THRESHOLD = Decimal("0.70")
COD_MEDIUM_RISK_THRESHOLD = Decimal("0.40")
COD_RURAL_RISK_BOOST = Decimal("0.20")
