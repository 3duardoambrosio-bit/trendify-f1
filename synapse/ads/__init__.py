# synapse/ads/__init__.py
from .ads_intelligence import (
    MetaAdsIntelligence,
    TikTokAdsIntelligence,
    GoogleAdsIntelligence,
    AudienceConfig,
    BudgetConfig,
    CreativeSpec,
    Platform,
    CampaignObjective,
    BidStrategy,
    PlacementType,
    get_platform_intelligence,
    calculate_test_budget,
    estimate_results,
)

__all__ = [
    "MetaAdsIntelligence",
    "TikTokAdsIntelligence",
    "GoogleAdsIntelligence",
    "AudienceConfig",
    "BudgetConfig",
    "CreativeSpec",
    "Platform",
    "CampaignObjective",
    "BidStrategy",
    "PlacementType",
    "get_platform_intelligence",
    "calculate_test_budget",
    "estimate_results",
]
