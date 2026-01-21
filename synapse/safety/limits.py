from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RiskLimits:
    # Capital protection (fractions, not percents)
    daily_loss_limit: float = 0.05           # 5% of monthly budget
    spend_rate_anomaly_mult: float = 3.0     # 3x expected spend-rate in window
    max_single_campaign_share: float = 0.25  # 25% concentration cap


@dataclass(frozen=True)
class RiskSnapshot:
    monthly_budget: float
    expected_spend_rate_4h: float  # currency per 4h
    actual_spend_4h: float         # currency spent in last 4h
    daily_loss: float              # currency lost today (negative profit)


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: Optional[str] = None


def evaluate_risk(limits: RiskLimits, snap: RiskSnapshot) -> RiskDecision:
    # Daily loss limit
    if snap.monthly_budget > 0:
        if snap.daily_loss > snap.monthly_budget * limits.daily_loss_limit:
            return RiskDecision(False, "DAILY_LOSS_LIMIT_EXCEEDED")

    # Spend-rate anomaly
    if snap.expected_spend_rate_4h > 0:
        if snap.actual_spend_4h > snap.expected_spend_rate_4h * limits.spend_rate_anomaly_mult:
            return RiskDecision(False, "SPEND_RATE_ANOMALY")

    return RiskDecision(True, None)
