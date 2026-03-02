from __future__ import annotations

"""
OXXO Payment Validator — A-02.

En este sistema, fijamos límites operativos:
- max_amount_mxn = 10,000
- min_amount_mxn = 20

Si el monto del carrito excede max, OXXO NO debe ofrecerse.
También validamos mínimo.

__MARKER__ embedded in module constant below.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import deal

__MARKER__ = "SESSION_S11_oxxo_validator_2026-03-02"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OxxoConfig:
    max_amount_mxn: Decimal = Decimal("10000")
    min_amount_mxn: Decimal = Decimal("20")
    expiry_hours: int = 72
    reminder_hours: int = 48


@dataclass(frozen=True)
class OxxoValidationResult:
    allowed: bool
    reason: str
    cart_amount: Decimal


class OxxoValidator:
    def __init__(self, config: OxxoConfig | None = None) -> None:
        self._config = config or OxxoConfig()

    @deal.pre(lambda self, cart_amount_mxn: isinstance(cart_amount_mxn, Decimal) and cart_amount_mxn >= Decimal("0"))
    @deal.post(lambda result: isinstance(result.allowed, bool))
    def validate_cart(self, cart_amount_mxn: Decimal) -> OxxoValidationResult:
        if cart_amount_mxn > self._config.max_amount_mxn:
            return OxxoValidationResult(False, "exceeds_oxxo_limit_10000", cart_amount_mxn)
        if cart_amount_mxn < self._config.min_amount_mxn:
            return OxxoValidationResult(False, "below_oxxo_minimum_20", cart_amount_mxn)
        return OxxoValidationResult(True, "ok", cart_amount_mxn)

    def calculate_expiry(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=self._config.expiry_hours)

    def needs_reminder(self, voucher_created_at: datetime) -> bool:
        dt = voucher_created_at
        if dt.tzinfo is None:
            log.warning("voucher_created_at naive; assuming UTC")
            dt = dt.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - dt
        return elapsed >= timedelta(hours=self._config.reminder_hours)
