# synapse/ads/ads_intelligence.py
"""
Ads Intelligence - Best practices y estrategias para plataformas de ads.

Contiene:
- Meta Ads (Facebook/Instagram) strategies
- TikTok Ads strategies
- Google Ads strategies (remarketing)
- Audience targeting por nicho
- Budget allocation
- Creative testing frameworks (DCT)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class Platform(Enum):
    META = "meta"
    TIKTOK = "tiktok"
    GOOGLE = "google"


class CampaignObjective(Enum):
    AWARENESS = "awareness"
    TRAFFIC = "traffic"
    ENGAGEMENT = "engagement"
    LEADS = "leads"
    CONVERSIONS = "conversions"
    SALES = "sales"


class BidStrategy(Enum):
    LOWEST_COST = "lowest_cost"
    COST_CAP = "cost_cap"
    BID_CAP = "bid_cap"
    ROAS_TARGET = "roas_target"


class PlacementType(Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


@dataclass
class AudienceConfig:
    """Configuración de audiencia."""
    name: str
    geo: List[str] = field(default_factory=lambda: ["MX"])
    age_min: int = 18
    age_max: int = 65
    gender: str = "all"
    languages: List[str] = field(default_factory=lambda: ["es"])
    interests: List[str] = field(default_factory=list)
    behaviors: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    lookalike_source: str = ""
    lookalike_percent: float = 0.0
    custom_audience_id: str = ""


@dataclass
class BudgetConfig:
    """Configuración de presupuesto."""
    daily_budget_usd: float = 50.0
    lifetime_budget_usd: float = 0.0
    bid_strategy: BidStrategy = BidStrategy.LOWEST_COST
    cost_cap_usd: float = 0.0
    roas_target: float = 0.0

    # Allocation
    testing_percent: float = 70.0
    scaling_percent: float = 30.0


@dataclass
class CreativeSpec:
    """Especificación de creative."""
    format: str  # image, video, carousel, collection
    aspect_ratio: str  # 1:1, 9:16, 16:9, 4:5
    duration_seconds: int = 0
    has_sound: bool = True
    has_captions: bool = True
    cta_type: str = "shop_now"


# ============================================================
# META ADS INTELLIGENCE
# ============================================================

class MetaAdsIntelligence:
    """
    Best practices y estrategias para Meta Ads (Facebook/Instagram).

    Enfoque:
    - Testing (hooks/ángulos/formatos)
    - Scaling (duplicar ganadores con control)
    - Retargeting (capturar intención)
    """

    # Benchmarks MX Ecommerce (heurísticas internas; se calibran con data real)
    BENCHMARKS_MX = {
        "ctr_avg": 1.0,          # %
        "ctr_good": 1.5,         # %
        "ctr_excellent": 2.5,    # %
        "cpm_avg": 8.0,          # USD
        "cpm_range": (3.0, 15.0),
        "cpa_avg": 15.0,         # USD
        "cvr_avg": 1.5,          # %
        "roas_breakeven": 1.0,
        "roas_good": 2.0,
        "roas_excellent": 3.0,
    }

    OBJECTIVES_BY_PHASE = {
        "testing": CampaignObjective.CONVERSIONS,
        "scaling": CampaignObjective.CONVERSIONS,
        "retargeting": CampaignObjective.CONVERSIONS,
        "awareness": CampaignObjective.AWARENESS,
    }

    PLACEMENTS_RECOMMENDED = {
        "feed": ["facebook_feed", "instagram_feed"],
        "stories": ["facebook_stories", "instagram_stories"],
        "reels": ["instagram_reels", "facebook_reels"],
        "all": [
            "facebook_feed", "instagram_feed",
            "facebook_stories", "instagram_stories",
            "instagram_reels", "facebook_reels"
        ],
    }

    CREATIVE_SPECS = {
        "feed": CreativeSpec(format="video", aspect_ratio="1:1", duration_seconds=15),
        "stories": CreativeSpec(format="video", aspect_ratio="9:16", duration_seconds=15),
        "reels": CreativeSpec(format="video", aspect_ratio="9:16", duration_seconds=15),
        "carousel": CreativeSpec(format="carousel", aspect_ratio="1:1", duration_seconds=0),
    }

    @classmethod
    def get_recommended_structure(cls, budget_daily: float) -> Dict[str, Any]:
        """Estructura recomendada de campaña para testing."""
        return {
            "campaign": {
                "objective": "CONVERSIONS",
                "budget_optimization": "CBO",
                "daily_budget_usd": float(budget_daily),
                "bid_strategy": "LOWEST_COST",
            },
            "ad_sets": [
                {"name": "Broad - Interest Stack", "targeting": "broad_interests", "budget_percent": 40},
                {"name": "Lookalike 1%", "targeting": "lookalike_1", "budget_percent": 30},
                {"name": "Retargeting - Engaged", "targeting": "retargeting", "budget_percent": 30},
            ],
            "ads_per_adset": 3,
            "testing_duration_days": 3,
            "min_spend_per_ad": 10,
        }

    @classmethod
    def get_audience_for_niche(cls, niche_id: str) -> AudienceConfig:
        """Audiencia recomendada por nicho."""
        NICHE_AUDIENCES = {
            "audio_personal": AudienceConfig(
                name="Audio Enthusiasts MX",
                age_min=18, age_max=45,
                interests=["música", "podcasts", "gaming", "tecnología", "fitness"],
                behaviors=["compradores online", "early adopters"],
            ),
            "skincare_tools": AudienceConfig(
                name="Skincare MX",
                age_min=20, age_max=45,
                gender="female",
                interests=["skincare", "belleza", "cuidado personal", "bienestar"],
            ),
            "pet_accessories": AudienceConfig(
                name="Pet Owners MX",
                age_min=25, age_max=55,
                interests=["mascotas", "perros", "gatos", "animales"],
                behaviors=["dueños de mascotas"],
            ),
            "home_organization": AudienceConfig(
                name="Home Organization MX",
                age_min=25, age_max=55,
                gender="female",
                interests=["decoración", "hogar", "organización", "minimalismo"],
            ),
            "led_lights": AudienceConfig(
                name="LED & Decor MX",
                age_min=18, age_max=40,
                interests=["decoración", "gaming", "tecnología", "TikTok"],
            ),
        }
        return NICHE_AUDIENCES.get(niche_id, AudienceConfig(name="Broad MX"))

    @classmethod
    def get_testing_framework(cls) -> Dict[str, Any]:
        """Framework de testing creativo (DCT - Dynamic Creative Testing)."""
        return {
            "phase_1_hooks": {
                "duration_days": 2,
                "budget_per_hook": 5,
                "hooks_to_test": 5,
                "metric": "hook_rate",
                "threshold": 15.0,  # %
                "action": "Kill hooks below threshold",
            },
            "phase_2_angles": {
                "duration_days": 2,
                "budget_per_angle": 10,
                "angles_to_test": 3,
                "metric": "ctr",
                "threshold": 1.0,  # %
                "action": "Scale winning angles",
            },
            "phase_3_scale": {
                "duration_days": 5,
                "budget_multiplier": 2.0,
                "metric": "cpa",
                "threshold_multiplier": 1.5,
                "action": "Graduate or kill",
            },
        }

    @classmethod
    def calculate_budget_allocation(cls, total_budget: float, phase: str) -> Dict[str, float]:
        """Calcula distribución de presupuesto."""
        total_budget = float(total_budget)
        if phase == "testing":
            return {
                "cold_traffic": total_budget * 0.70,
                "retargeting": total_budget * 0.20,
                "reserve": total_budget * 0.10,
            }
        if phase == "scaling":
            return {
                "winning_ads": total_budget * 0.60,
                "new_tests": total_budget * 0.25,
                "retargeting": total_budget * 0.15,
            }
        return {"total": total_budget}


# ============================================================
# TIKTOK ADS INTELLIGENCE
# ============================================================

class TikTokAdsIntelligence:
    """
    Best practices para TikTok Ads.

    Principios:
    - Contenido nativo (que no huela a anuncio)
    - Hook brutal en 3s
    - Faceless-friendly
    """

    BENCHMARKS_MX = {
        "ctr_avg": 0.8,
        "ctr_good": 1.2,
        "cpm_avg": 5.0,
        "cpm_range": (2.0, 10.0),
        "hook_rate_good": 20.0,   # % que ve 3s
        "watch_time_good": 50.0,  # % del video
    }

    CREATIVE_BEST_PRACTICES = {
        "duration": "15-30 seconds optimal",
        "hook": "First 3 seconds critical",
        "format": "9:16 vertical only",
        "sound": "Use trending sounds",
        "text": "Captions required (muchos ven sin audio)",
        "style": "Native, not polished",
        "cta": "Soft CTA, not aggressive",
    }

    FACELESS_FORMATS = [
        "hands_only",
        "unboxing",
        "before_after",
        "text_story",
        "voiceover_demo",
        "asmr_product",
        "pov_style",
        "tutorial_hands",
    ]

    @classmethod
    def get_ad_structure(cls, budget_daily: float) -> Dict[str, Any]:
        """Estructura recomendada TikTok."""
        return {
            "campaign": {
                "objective": "CONVERSIONS",
                "budget_mode": "BUDGET_MODE_DAY",
                "daily_budget_usd": float(budget_daily),
            },
            "ad_groups": [
                {"name": "Broad Targeting", "targeting": "broad", "placements": ["tiktok"], "budget_percent": 60},
                {"name": "Interest Based", "targeting": "interests", "placements": ["tiktok"], "budget_percent": 40},
            ],
            "creatives_per_group": 3,
            "testing_duration_days": 3,
        }

    @classmethod
    def get_creative_guidelines(cls, niche_id: str) -> Dict[str, Any]:
        """Guidelines de creative por nicho (MVP)."""
        return {
            "format": "video_9_16",
            "duration_range": (15, 30),
            "hook_duration": 3,
            "recommended_formats": cls.FACELESS_FORMATS[:4],
            "sound": "trending_or_original",
            "captions": "required",
            "cta_style": "soft",
            "editing_style": "native_not_polished",
        }


# ============================================================
# GOOGLE ADS INTELLIGENCE (REMARKETING)
# ============================================================

class GoogleAdsIntelligence:
    """Google Ads strategies - principalmente remarketing."""

    REMARKETING_AUDIENCES = {
        "cart_abandoners": {"description": "Agregaron al carrito y no compraron", "lookback_days": 7, "priority": "high"},
        "product_viewers": {"description": "Vieron producto", "lookback_days": 14, "priority": "medium"},
        "site_visitors": {"description": "Visitantes del sitio", "lookback_days": 30, "priority": "low"},
    }

    @classmethod
    def get_remarketing_structure(cls, budget_daily: float) -> Dict[str, Any]:
        """Estructura de remarketing."""
        return {
            "campaign_type": "DISPLAY",
            "strategy": "remarketing",
            "daily_budget_usd": float(budget_daily),
            "audiences": list(cls.REMARKETING_AUDIENCES.keys()),
            "ad_formats": ["responsive_display", "dynamic_remarketing"],
        }


# ============================================================
# HELPERS
# ============================================================

def get_platform_intelligence(platform: str):
    """Factory para obtener intelligence por plataforma."""
    mapping = {
        "meta": MetaAdsIntelligence,
        "tiktok": TikTokAdsIntelligence,
        "google": GoogleAdsIntelligence,
    }
    return mapping.get(platform, MetaAdsIntelligence)


def calculate_test_budget(cpa_target: float, tests_count: int, confidence_conversions: int = 3) -> float:
    """CPA_target × conversiones_para_confianza × cantidad_de_tests"""
    return float(cpa_target) * float(confidence_conversions) * float(tests_count)


def estimate_results(budget: float, cpm: float, ctr: float, cvr: float) -> Dict[str, float]:
    """Estima resultados basado en benchmarks."""
    budget = float(budget)
    cpm = float(cpm)
    ctr = float(ctr)
    cvr = float(cvr)

    impressions = (budget / cpm) * 1000 if cpm > 0 else 0.0
    clicks = impressions * (ctr / 100.0)
    conversions = clicks * (cvr / 100.0)
    cpa = (budget / conversions) if conversions > 0 else float("inf")

    return {"impressions": impressions, "clicks": clicks, "conversions": conversions, "cpa": cpa}
