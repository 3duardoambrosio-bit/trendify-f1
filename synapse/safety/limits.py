from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from numbers import Real
from typing import Optional, Union

import deal

Number = Union[Decimal, int, str, Real]

_MONEY_Q = Decimal("0.01")
_RATIO_Q = Decimal("0.0001")


def _d(x: Number) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool):
        raise TypeError("bool is not a valid numeric input")
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, Real):
        # Real includes floats; repr preserves precision better than str for Decimal conversion.
        return Decimal(repr(x))
    return Decimal(str(x))


def _q_money(x: Decimal) -> Decimal:
    return x.quantize(_MONEY_Q, rounding=ROUND_HALF_EVEN)


def _q_ratio(x: Decimal) -> Decimal:
    return x.quantize(_RATIO_Q, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class RiskLimits:
    # Capital protection (fractions, not percents)
    daily_loss_limit: Decimal = Decimal("0.05")          # 5% of monthly budget
    spend_rate_anomaly_mult: Decimal = Decimal("3.0")    # 3x expected spend-rate in window
    max_single_campaign_share: Decimal = Decimal("0.25") # reserved for future concentration cap
    auto_killswitch_threshold: Decimal = Decimal("0.80") # 80% of budget in 24h → auto-killswitch

    def __post_init__(self) -> None:
        object.__setattr__(self, "daily_loss_limit", _q_ratio(_d(self.daily_loss_limit)))
        object.__setattr__(self, "spend_rate_anomaly_mult", _q_ratio(_d(self.spend_rate_anomaly_mult)))
        object.__setattr__(self, "max_single_campaign_share", _q_ratio(_d(self.max_single_campaign_share)))
        object.__setattr__(self, "auto_killswitch_threshold", _q_ratio(_d(self.auto_killswitch_threshold)))


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    monthly_budget: Decimal
    expected_spend_rate_4h: Decimal  # currency per 4h
    actual_spend_4h: Decimal         # currency spent in last 4h
    daily_loss: Decimal              # currency lost today

    def __post_init__(self) -> None:
        object.__setattr__(self, "monthly_budget", _q_money(_d(self.monthly_budget)))
        object.__setattr__(self, "expected_spend_rate_4h", _q_money(_d(self.expected_spend_rate_4h)))
        object.__setattr__(self, "actual_spend_4h", _q_money(_d(self.actual_spend_4h)))
        object.__setattr__(self, "daily_loss", _q_money(_d(self.daily_loss)))


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: Optional[str] = None


@deal.pre(lambda limits, snap: limits is not None, message="limits required")
@deal.pre(lambda limits, snap: snap is not None, message="snapshot required")
@deal.post(lambda result: isinstance(result, RiskDecision), message="returns RiskDecision")
@deal.raises(deal.PreContractError, deal.RaisesContractError)
def evaluate_risk(limits: RiskLimits, snap: RiskSnapshot) -> RiskDecision:
    # Auto-killswitch: 24h spend >= 80% of budget (checked first — highest severity)
    if snap.monthly_budget > 0:
        if snap.daily_loss >= (snap.monthly_budget * limits.auto_killswitch_threshold):
            return RiskDecision(False, "AUTO_KILLSWITCH_THRESHOLD_EXCEEDED")

    if snap.monthly_budget > 0:
        if snap.daily_loss > (snap.monthly_budget * limits.daily_loss_limit):
            return RiskDecision(False, "DAILY_LOSS_LIMIT_EXCEEDED")

    if snap.expected_spend_rate_4h > 0:
        if snap.actual_spend_4h > (snap.expected_spend_rate_4h * limits.spend_rate_anomaly_mult):
            return RiskDecision(False, "SPEND_RATE_ANOMALY")

    return RiskDecision(True, None)
