# V3GAP:B-05_advantage_plus_2025

from __future__ import annotations

"""
Advantage+ Campaign Configuration — B-05.

Genera payloads para campañas Advantage+ Shopping (ASC).
Meta recomienda ASC para e-commerce. Minimo 7 dias sin tocar.

__MARKER__ embedded in module constant below.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Tuple, Any
import logging

import deal

__MARKER__ = "SESSION_S10_advantage_plus_20260228"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdvantagePlusConfig:
    optimization_goal: str = "OFFSITE_CONVERSIONS"
    attribution_window: str = "7d_click_1d_view"
    min_budget_daily_usd: Decimal = Decimal("5")
    learning_phase_days: int = 7
    creative_count_min: int = 3
    creative_count_max: int = 10


class AdvantagePlusCampaignBuilder:
    def __init__(self, config: AdvantagePlusConfig):
        self._config = config

    @deal.pre(lambda self, creatives_count, pixel_events, budget_daily=None: creatives_count >= 0)
    @deal.pre(lambda self, creatives_count, pixel_events, budget_daily=None: isinstance(pixel_events, list))
    def validate_prerequisites(
        self,
        creatives_count: int,
        pixel_events: List[str],
        budget_daily: Decimal | None = None,
    ) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        if creatives_count < self._config.creative_count_min:
            errors.append("insufficient_creatives(<3)")

        events = {str(e) for e in pixel_events}
        if ("Purchase" not in events) and ("AddToCart" not in events):
            errors.append("missing_required_pixel_events(Purchase|AddToCart)")

        if budget_daily is not None and budget_daily < self._config.min_budget_daily_usd:
            errors.append("budget_below_min_daily_usd")

        return (len(errors) == 0), errors

    @deal.pre(lambda self, product, budget_daily, creatives: budget_daily > 0)
    @deal.post(lambda result: isinstance(result, dict))
    @deal.post(lambda result: ("campaign_objective" in result) and ("optimization_goal" in result))
    def build_campaign_payload(self, product: Any, budget_daily: Decimal, creatives: List[Any]) -> Dict[str, Any]:
        creatives_count = len(creatives)

        ok, errors = self.validate_prerequisites(
            creatives_count=creatives_count,
            pixel_events=getattr(product, "pixel_events", ["Purchase"]),
            budget_daily=budget_daily,
        )
        if not ok:
            raise ValueError("Advantage+ prerequisites failed: " + ",".join(errors))

        if budget_daily < self._config.min_budget_daily_usd:
            raise ValueError("Budget below min for Advantage+ learning.")

        payload: Dict[str, Any] = {
            "campaign_objective": "SALES",
            "optimization_goal": self._config.optimization_goal,
            "attribution_window": self._config.attribution_window,
            "budget_daily_usd": str(budget_daily),
            "creatives_count": creatives_count,
            "product_ref": getattr(product, "sku", None) or getattr(product, "id", None) or str(product),
        }
        return payload

    @deal.pre(lambda self, budget_daily: budget_daily > 0)
    def estimate_learning_phase_cost(self, budget_daily: Decimal) -> Decimal:
        return Decimal(str(self._config.learning_phase_days)) * budget_daily