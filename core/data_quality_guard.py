from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal


Action = Literal["OK", "VERIFY", "BLOCK"]


@dataclass(frozen=True)
class DataQualityReport:
    score: float  # 0..1
    flags: List[str]
    action: Action


class DataQualityGuard:
    """
    Conservative data sanity checker for supplier evidence.
    Goal: downgrade confidence / block launch when evidence smells like fantasy.
    """

    def evaluate(self, evidence: Dict[str, Any]) -> DataQualityReport:
        flags: List[str] = []
        score = 1.0

        def penalize(amount: float, flag: str) -> None:
            nonlocal score
            score *= amount
            flags.append(flag)

        price = float(evidence.get("price_usd", 0.0) or 0.0)
        ship = float(evidence.get("shipping_usd_to_mexico", evidence.get("shipping_usd", 0.0)) or 0.0)
        rating = float(evidence.get("rating", 0.0) or 0.0)
        reviews = int(evidence.get("reviews", 0) or 0)
        sold = int(evidence.get("sold", 0) or 0)

        # Hard invalids
        if price <= 0:
            return DataQualityReport(0.0, ["price_invalid"], "BLOCK")
        if ship < 0:
            return DataQualityReport(0.0, ["shipping_invalid"], "BLOCK")
        if rating < 0 or rating > 5:
            return DataQualityReport(0.0, ["rating_out_of_range"], "BLOCK")
        if reviews < 0 or sold < 0:
            return DataQualityReport(0.0, ["negative_counts"], "BLOCK")

        # Soft anomalies
        if rating < 4.3:
            penalize(0.85, "rating_low")

        # weird ratio: too many reviews vs sold is suspicious
        if sold > 0:
            rr = reviews / max(sold, 1)
            if rr > 0.35:
                penalize(0.80, "reviews_to_sold_suspicious")

        # ultra-cheap + huge volume smells like bait
        if price < 6 and sold >= 3000:
            penalize(0.75, "price_too_low_for_volume")

        # clamp
        score = max(0.0, min(1.0, score))

        if score < 0.55:
            return DataQualityReport(score, flags, "BLOCK")
        if score < 0.75:
            return DataQualityReport(score, flags, "VERIFY")
        return DataQualityReport(score, flags, "OK")