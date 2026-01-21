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
