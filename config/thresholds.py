from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class ScoringWeights:
    margin_weight: float = 0.28
    demand_weight: float = 0.22
    competition_weight: float = 0.20
    trend_weight: float = 0.15
    supplier_weight: float = 0.15
    def total(self) -> float:
        return self.margin_weight + self.demand_weight + self.competition_weight + self.trend_weight + self.supplier_weight
    def validate(self) -> None:
        t = self.total()
        if abs(t - 1.0) > 1e-6:
            raise ValueError(f"ScoringWeights must sum to 1.0 +/- 1e-6, got {t}")

@dataclass(frozen=True)
class ScoringThresholds:
    min_confidence: float = 0.75
    min_margin_pct: float = 0.65
    min_demand_score: float = 0.68
    min_overall_score: float = 0.60

@dataclass(frozen=True)
class CatalogScannerFilters:
    min_price_mxn: Decimal = Decimal("40.0")
    max_price_mxn: Decimal = Decimal("2000.0")
    min_margin_mxn: Decimal = Decimal("100.0")
    min_rating: float = 3.5
    min_reviews: int = 100

@dataclass(frozen=True)
class HttpTimeouts:
    default_timeout_s: int = 30
    meta_api_timeout_s: int = 60
    meta_upload_timeout_s: int = 120
    shopify_timeout_s: int = 45
    dropi_timeout_s: int = 60

SCORING_WEIGHTS = ScoringWeights()
SCORING_THRESHOLDS = ScoringThresholds()
CATALOG_FILTERS = CatalogScannerFilters()
HTTP_TIMEOUTS = HttpTimeouts()