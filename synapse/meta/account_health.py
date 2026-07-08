# V3GAP:B-01_account_health_monitor

# V3GAP:account_health_in_pipeline

from __future__ import annotations

"""
Account Health Monitor — account_health_in_pipeline.

Chequea indicadores de riesgo antes de publicar/escalar.
Si la cuenta está en zona de riesgo -> bloquear publicación.

__MARKER__ embedded in module constant below.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional
import logging

import deal

__MARKER__ = "SESSION_S10_account_health_20260228"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountMetrics:
    ad_disapproval_rate: float
    spend_velocity_ratio: float
    account_age_days: int
    has_policy_violation: bool
    feedback_score: Optional[float] = None


@dataclass(frozen=True)
class AccountHealthConfig:
    disapproval_yellow: Decimal = Decimal("0.10")
    disapproval_red: Decimal = Decimal("0.20")
    velocity_yellow: Decimal = Decimal("3.0")
    warm_up_age_days: int = 10


@dataclass(frozen=True)
class AccountHealthStatus:
    is_healthy: bool
    risk_level: str  # green/yellow/red
    issues: List[str]
    can_publish: bool
    can_scale: bool


class AccountHealthChecker:
    def __init__(self, config: AccountHealthConfig):
        self._config = config

    @deal.pre(lambda self, metrics: 0.0 <= metrics.ad_disapproval_rate <= 1.0)
    @deal.pre(lambda self, metrics: metrics.spend_velocity_ratio >= 0.0)
    @deal.pre(lambda self, metrics: metrics.account_age_days >= 0)
    def check(self, metrics: AccountMetrics) -> AccountHealthStatus:
        issues: List[str] = []
        risk = "green"
        can_publish = True
        can_scale = True

        dis = Decimal(str(metrics.ad_disapproval_rate))
        vel = Decimal(str(metrics.spend_velocity_ratio))

        if metrics.has_policy_violation:
            issues.append("policy_violation=true")
            risk = "red"
            can_publish = False
            can_scale = False

        if dis > self._config.disapproval_red:
            issues.append(f"ad_disapproval_rate>{self._config.disapproval_red}")
            risk = "red"
            can_publish = False
            can_scale = False
        elif dis > self._config.disapproval_yellow:
            issues.append(f"ad_disapproval_rate>{self._config.disapproval_yellow}")
            if risk != "red":
                risk = "yellow"
            can_scale = False

        if vel > self._config.velocity_yellow:
            issues.append(f"spend_velocity_ratio>{self._config.velocity_yellow}")
            if risk != "red":
                risk = "yellow"
            can_scale = False

        if metrics.account_age_days < self._config.warm_up_age_days:
            issues.append("warm_up_required(account_age_days<10)")
            if risk == "green":
                risk = "yellow"
            can_scale = False

        is_healthy = (risk != "red")

        return AccountHealthStatus(
            is_healthy=is_healthy,
            risk_level=risk,
            issues=issues,
            can_publish=can_publish,
            can_scale=can_scale,
        )