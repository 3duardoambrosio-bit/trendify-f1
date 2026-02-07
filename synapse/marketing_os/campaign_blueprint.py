# synapse/marketing_os/campaign_blueprint.py
"""
Campaign Blueprint - Planes ejecutables por plataforma.

Genera configs listas para Meta, TikTok, Google.
No ideas, EJECUTABLES.
"""


from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import json
from synapse.infra.time_utc import now_utc, isoformat_z


class Platform(Enum):
    META = "meta"
    TIKTOK = "tiktok"
    GOOGLE = "google"


class Objective(Enum):
    CONVERSIONS = "conversions"
    TRAFFIC = "traffic"
    ENGAGEMENT = "engagement"
    AWARENESS = "awareness"


class BudgetType(Enum):
    DAILY = "daily"
    LIFETIME = "lifetime"


@dataclass
class TargetingConfig:
    """Configuracion de targeting."""
    geo: List[str] = field(default_factory=lambda: ["MX"])
    age_min: int = 18
    age_max: int = 65
    gender: str = "all"
    placements: List[str] = field(default_factory=lambda: ["feed", "stories", "reels"])
    interests: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)


@dataclass
class CreativeSlot:
    """Slot de creative en el blueprint."""
    slot_id: str
    content_type: str  # hook, script_15s, primary_text
    variant_id: str
    content_preview: str
    quality_score: float = 0.0


@dataclass
class AdSetConfig:
    """Configuracion de ad set."""
    adset_name: str
    targeting: TargetingConfig
    optimization: str = "PURCHASE"
    bid_strategy: str = "LOWEST_COST"
    budget_usd: float = 10.0
    creatives: List[CreativeSlot] = field(default_factory=list)


@dataclass 
class CampaignBlueprint:
    """Blueprint completo de campana."""
    blueprint_id: str
    product_id: str
    product_name: str
    platform: Platform
    objective: Objective
    
    # Budget
    budget_type: BudgetType = BudgetType.DAILY
    total_budget_usd: float = 50.0
    
    # Structure
    adsets: List[AdSetConfig] = field(default_factory=list)
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    estimated_reach: str = "10K-50K"
    estimated_cpm: str = "$5-15"
    
    # Tracking
    utm_params: Dict[str, str] = field(default_factory=dict)
    pixel_events: List[str] = field(default_factory=lambda: ["ViewContent", "AddToCart", "Purchase"])
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["platform"] = self.platform.value
        d["objective"] = self.objective.value
        d["budget_type"] = self.budget_type.value
        return d
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class BlueprintGenerator:
    """
    Genera blueprints de campana por plataforma.
    
    Uso:
        gen = BlueprintGenerator()
        blueprint = gen.generate_meta_blueprint(product_id, kit)
    """
    
    def __init__(self, default_budget: float = 50.0):
        self.default_budget = default_budget
    
    def generate_meta_blueprint(
        self,
        product_id: str,
        product_name: str,
        kit: Dict[str, Any],
        budget_usd: float = None,
        targeting: Optional[TargetingConfig] = None,
    ) -> CampaignBlueprint:
        """Genera blueprint para Meta (Facebook/Instagram)."""
        
        budget = budget_usd or self.default_budget
        targeting = targeting or TargetingConfig()
        
        # Create ad sets by angle
        adsets = []
        
        # AdSet 1: Test Hooks (multiple hooks, same targeting)
        hook_creatives = []
        for i, hook in enumerate(kit.get("hooks", [])[:5]):
            hook_creatives.append(CreativeSlot(
                slot_id=f"hook_{i+1}",
                content_type="hook",
                variant_id=hook.get("variant_id", f"H{i+1}"),
                content_preview=hook.get("content", "")[:100],
                quality_score=hook.get("quality_score", 0),
            ))
        
        adsets.append(AdSetConfig(
            adset_name=f"{product_id}_hooks_test",
            targeting=targeting,
            optimization="PURCHASE",
            budget_usd=budget * 0.6,
            creatives=hook_creatives,
        ))
        
        # AdSet 2: Retargeting (engaged users)
        retarget_targeting = TargetingConfig(
            geo=targeting.geo,
            age_min=targeting.age_min,
            age_max=targeting.age_max,
            placements=["feed", "stories"],
        )
        
        primary_creatives = []
        for i, text in enumerate(kit.get("primary_texts", [])[:3]):
            primary_creatives.append(CreativeSlot(
                slot_id=f"primary_{i+1}",
                content_type="primary_text",
                variant_id=f"PT{i+1}",
                content_preview=text.get("content", "")[:100],
                quality_score=text.get("quality_score", 0),
            ))
        
        adsets.append(AdSetConfig(
            adset_name=f"{product_id}_retarget",
            targeting=retarget_targeting,
            optimization="PURCHASE",
            budget_usd=budget * 0.4,
            creatives=primary_creatives,
        ))
        
        return CampaignBlueprint(
            blueprint_id=f"meta_{product_id}_{now_utc().strftime('%Y%m%d')}",
            product_id=product_id,
            product_name=product_name,
            platform=Platform.META,
            objective=Objective.CONVERSIONS,
            budget_type=BudgetType.DAILY,
            total_budget_usd=budget,
            adsets=adsets,
            utm_params={
                "utm_source": "meta",
                "utm_medium": "paid",
                "utm_campaign": f"P{product_id}",
            },
        )
    
    def generate_tiktok_blueprint(
        self,
        product_id: str,
        product_name: str,
        kit: Dict[str, Any],
        budget_usd: float = None,
    ) -> CampaignBlueprint:
        """Genera blueprint para TikTok."""
        
        budget = budget_usd or self.default_budget
        
        # TikTok: focus on video scripts
        script_creatives = []
        for i, script in enumerate(kit.get("scripts_15s", [])[:5]):
            script_creatives.append(CreativeSlot(
                slot_id=f"script_{i+1}",
                content_type="script_15s",
                variant_id=script.get("variant_id", f"S{i+1}"),
                content_preview=script.get("content", "")[:100],
                quality_score=script.get("quality_score", 0),
            ))
        
        targeting = TargetingConfig(
            geo=["MX"],
            age_min=18,
            age_max=45,
            placements=["tiktok_feed"],
        )
        
        adsets = [AdSetConfig(
            adset_name=f"{product_id}_tiktok_test",
            targeting=targeting,
            optimization="CONVERSION",
            bid_strategy="LOWEST_COST",
            budget_usd=budget,
            creatives=script_creatives,
        )]
        
        return CampaignBlueprint(
            blueprint_id=f"tiktok_{product_id}_{now_utc().strftime('%Y%m%d')}",
            product_id=product_id,
            product_name=product_name,
            platform=Platform.TIKTOK,
            objective=Objective.CONVERSIONS,
            total_budget_usd=budget,
            adsets=adsets,
            estimated_cpm="$3-10",
            utm_params={
                "utm_source": "tiktok",
                "utm_medium": "paid",
                "utm_campaign": f"P{product_id}",
            },
        )
    
    def generate_all_platforms(
        self,
        product_id: str,
        product_name: str,
        kit: Dict[str, Any],
        total_budget: float = 100.0,
    ) -> Dict[str, CampaignBlueprint]:
        """Genera blueprints para todas las plataformas."""
        
        # Split budget: 60% Meta, 40% TikTok
        return {
            "meta": self.generate_meta_blueprint(
                product_id, product_name, kit, 
                budget_usd=total_budget * 0.6
            ),
            "tiktok": self.generate_tiktok_blueprint(
                product_id, product_name, kit,
                budget_usd=total_budget * 0.4
            ),
        }


def quick_blueprint(
    product_id: str,
    product_name: str,
    hooks: List[str],
    platform: str = "meta",
    budget: float = 50.0,
) -> CampaignBlueprint:
    """Helper para blueprint rapido."""
    kit = {
        "hooks": [{"content": h, "variant_id": f"H{i}", "quality_score": 0.7} for i, h in enumerate(hooks)],
        "primary_texts": [],
        "scripts_15s": [],
    }
    
    gen = BlueprintGenerator(default_budget=budget)
    
    if platform == "tiktok":
        return gen.generate_tiktok_blueprint(product_id, product_name, kit, budget)
    return gen.generate_meta_blueprint(product_id, product_name, kit, budget)
