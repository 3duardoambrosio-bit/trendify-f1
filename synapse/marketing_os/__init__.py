# synapse/marketing_os/__init__.py
"""
Marketing OS - Sistema de marketing automatizado F1.

Modulos:
- interrogation_engine: Cuestionamiento pre-lanzamiento
- quality_filter: Filtro dual de calidad
- creative_factory: Generacion de contenido
- wave_runner: Pipeline E2E
- experiment_engine: Stop-loss y scaling
- campaign_blueprint: Planes ejecutables
"""

from .models import (
    Emotion, Angle, InterrogationVerdict, ContentType, QualityDimension,
    ProductContext, InterrogationResult, GeneratedContent, AdKitManifest,
    Signal, MarketPulseMemo, Risk, QualityFilterResult,
)
from .interrogation_engine import InterrogationEngine, quick_interrogate
from .quality_filter import QualityFilter, ContractFilter, MetaFilter, quick_check
from .creative_factory import CreativeFactory, quick_generate
from .wave_runner import WaveRunner, WaveResult, run_wave, run_wave_from_csv
from .experiment_engine import (
    ExperimentEngine, ExperimentMetrics, ExperimentDecision,
    Decision, StopLossConfig, quick_evaluate
)
from .campaign_blueprint import (
    BlueprintGenerator, CampaignBlueprint, Platform, Objective,
    TargetingConfig, quick_blueprint
)

__all__ = [
    "Emotion", "Angle", "InterrogationVerdict", "ContentType", "QualityDimension",
    "ProductContext", "InterrogationResult", "GeneratedContent", "AdKitManifest",
    "Signal", "MarketPulseMemo", "Risk", "QualityFilterResult",
    "InterrogationEngine", "quick_interrogate",
    "QualityFilter", "ContractFilter", "MetaFilter", "quick_check",
    "CreativeFactory", "quick_generate",
    "WaveRunner", "WaveResult", "run_wave", "run_wave_from_csv",
    "ExperimentEngine", "ExperimentMetrics", "ExperimentDecision",
    "Decision", "StopLossConfig", "quick_evaluate",
    "BlueprintGenerator", "CampaignBlueprint", "Platform", "Objective",
    "TargetingConfig", "quick_blueprint",
]
# A8-R86I2 expert foundation public surface
from .expert_foundation import (
    ExpertAd,
    ExpertAdSet,
    ExpertAudience,
    ExpertCampaignStructure,
    ExpertHook,
    ExpertOffer,
    ExpertStopRules,
    MarketingExpertPack,
    build_marketing_expert_pack,
    pack_to_dict,
)

_EXPERT_FOUNDATION_EXPORTS = (
    "ExpertAd",
    "ExpertAdSet",
    "ExpertAudience",
    "ExpertCampaignStructure",
    "ExpertHook",
    "ExpertOffer",
    "ExpertStopRules",
    "MarketingExpertPack",
    "build_marketing_expert_pack",
    "pack_to_dict",
)

__all__ = tuple(dict.fromkeys(tuple(globals().get("__all__", ())) + _EXPERT_FOUNDATION_EXPORTS))
# A8-R87I1 first selling pack public surface
from .selling_pack import (
    FirstSellingPack,
    build_first_selling_pack,
    build_first_selling_pack_dict,
    first_selling_pack_to_dict,
)

_SELLING_PACK_EXPORTS = (
    "FirstSellingPack",
    "build_first_selling_pack",
    "build_first_selling_pack_dict",
    "first_selling_pack_to_dict",
)

__all__ = tuple(dict.fromkeys(tuple(globals().get("__all__", ())) + _SELLING_PACK_EXPORTS))
