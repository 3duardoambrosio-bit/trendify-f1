# synapse/marketing_os/models.py
"""
Models compartidos para Marketing OS.
Dataclasses y Enums que usan todos los módulos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
import hashlib
import json


# ============================================================
# ENUMS
# ============================================================

class Emotion(str, Enum):
    """Emociones primarias de compra."""
    STATUS = "status"
    CONTROL = "control"
    RELIEF = "alivio"
    BELONGING = "pertenencia"
    SECURITY = "seguridad"
    PLEASURE = "placer"


class Angle(str, Enum):
    """Ángulos de marketing."""
    DOLOR = "dolor"
    STATUS = "status"
    FUNCIONAL = "funcional"
    REGALO = "regalo"
    AHORRO = "ahorro"
    LIFESTYLE = "lifestyle"
    ANTICABLES = "anticables"


class InterrogationVerdict(str, Enum):
    """Veredictos de interrogación."""
    LAUNCH = "launch"
    NEEDS_WORK = "needs_work"
    BLOCK = "block"


class ContentType(str, Enum):
    """Tipos de contenido generado."""
    HOOK = "hook"
    SCRIPT_7S = "script_7s"
    SCRIPT_15S = "script_15s"
    SCRIPT_30S = "script_30s"
    PRIMARY_TEXT = "primary_text"
    HEADLINE = "headline"
    LANDING = "landing"


class QualityDimension(str, Enum):
    """Dimensiones de calidad para meta-filter."""
    CLARITY = "clarity"
    PERSUASION = "persuasion"
    DIFFERENTIATION = "differentiation"
    COMPLIANCE = "compliance"
    MEXICANIDAD = "mexicanidad"
    ACTIONABILITY = "actionability"


# ============================================================
# HELPERS
# ============================================================

def _now() -> str:
    """UTC timestamp ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _hash_dict(d: Dict) -> str:
    """Hash determinístico de un dict."""
    serialized = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


# ============================================================
# INPUT MODELS
# ============================================================

@dataclass
class ProductContext:
    """Contexto del producto para interrogación y generación."""
    product_id: str
    name: str
    category: str
    price: float
    cost: float
    description: str = ""
    images: List[str] = field(default_factory=list)
    
    # Optional enrichment
    target_audience: str = ""
    use_cases: List[str] = field(default_factory=list)
    unique_features: List[str] = field(default_factory=list)
    known_objections: List[str] = field(default_factory=list)
    competitor_weaknesses: List[str] = field(default_factory=list)
    
    @property
    def margin(self) -> float:
        """Margen bruto."""
        if self.price <= 0:
            return 0.0
        return (self.price - self.cost) / self.price
    
    @property
    def margin_pct(self) -> float:
        """Margen como porcentaje."""
        return self.margin * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "cost": self.cost,
            "margin_pct": round(self.margin_pct, 1),
            "description": self.description[:200] if self.description else "",
            "images_count": len(self.images),
        }
    
    def input_hash(self) -> str:
        """Hash para idempotencia."""
        return _hash_dict(self.to_dict())


@dataclass
class Wave05Input:
    """Input para Wave 05 Marketing Kit."""
    product: ProductContext
    
    # Config
    angles_to_use: List[Angle] = field(default_factory=lambda: [Angle.DOLOR, Angle.STATUS, Angle.FUNCIONAL])
    num_hooks: int = 10
    num_scripts_per_length: int = 5
    num_primary_texts: int = 10
    num_headlines: int = 10
    num_landing_skeletons: int = 5
    
    # Behavior
    skip_interrogation: bool = False
    force_regenerate: bool = False


# ============================================================
# OUTPUT MODELS
# ============================================================

@dataclass
class Risk:
    """Riesgo identificado."""
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    mitigation: str
    category: str = "general"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "severity": self.severity,
            "mitigation": self.mitigation,
            "category": self.category,
        }


@dataclass
class InterrogationResult:
    """Resultado de interrogación."""
    product_id: str
    product_name: str
    
    # Scores
    total_score: float
    framework_scores: Dict[str, float]
    
    # Findings
    emotion_primary: Optional[Emotion]
    emotion_secondary: Optional[Emotion]
    enemy: str
    job_to_be_done: str
    killing_objection: str
    objection_response: str
    differentiation: str
    
    # Recommendation
    recommended_angle: Angle
    angles_to_avoid: List[Angle]
    
    # Risks
    risks: List[Risk]
    compliance_flags: List[str]
    
    # Decision
    verdict: InterrogationVerdict
    blocking_reasons: List[str]
    recommendations: List[str]
    
    # Meta
    interrogated_at: str = field(default_factory=_now)
    input_hash: str = ""
    schema_version: str = "1.0.0"
    
    @property
    def passed(self) -> bool:
        return self.verdict == InterrogationVerdict.LAUNCH
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "total_score": round(self.total_score, 3),
            "framework_scores": {k: round(v, 3) for k, v in self.framework_scores.items()},
            "verdict": self.verdict.value,
            "passed": self.passed,
            "emotion_primary": self.emotion_primary.value if self.emotion_primary else None,
            "emotion_secondary": self.emotion_secondary.value if self.emotion_secondary else None,
            "enemy": self.enemy,
            "job_to_be_done": self.job_to_be_done,
            "killing_objection": self.killing_objection,
            "objection_response": self.objection_response,
            "differentiation": self.differentiation,
            "recommended_angle": self.recommended_angle.value,
            "angles_to_avoid": [a.value for a in self.angles_to_avoid],
            "risks": [r.to_dict() for r in self.risks],
            "compliance_flags": self.compliance_flags,
            "blocking_reasons": self.blocking_reasons,
            "recommendations": self.recommendations,
            "interrogated_at": self.interrogated_at,
            "input_hash": self.input_hash,
        }


@dataclass
class GeneratedContent:
    """Pieza de contenido generada."""
    content_type: ContentType
    content: str
    angle: Angle
    
    # Quality
    quality_score: float = 0.0
    quality_dimensions: Dict[str, float] = field(default_factory=dict)
    
    # Metadata
    why_it_works: str = ""
    compliance_risk: str = ""
    variant_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.content_type.value,
            "content": self.content,
            "angle": self.angle.value,
            "quality_score": round(self.quality_score, 3),
            "why_it_works": self.why_it_works,
            "compliance_risk": self.compliance_risk,
            "variant_id": self.variant_id,
        }


@dataclass
class ObjectionResponse:
    """Respuesta a objeción."""
    objection: str
    response: str
    evidence: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "objection": self.objection,
            "response": self.response,
            "evidence": self.evidence,
        }


@dataclass
class AdKitManifest:
    """Manifest del Ad Kit generado."""
    product_id: str
    product_name: str
    schema_version: str = "1.0.0"
    
    # Generation info
    generated_at: str = field(default_factory=_now)
    wave_id: str = ""
    
    # Content counts
    angles_used: List[str] = field(default_factory=list)
    hooks_count: int = 0
    scripts_7s_count: int = 0
    scripts_15s_count: int = 0
    scripts_30s_count: int = 0
    primary_texts_count: int = 0
    headlines_count: int = 0
    landing_skeletons_count: int = 0
    
    # Quality
    quality_score: float = 0.0
    compliance_flags: List[str] = field(default_factory=list)
    
    # Interrogation
    interrogation_verdict: str = ""
    interrogation_score: float = 0.0
    
    # Hashes
    input_hash: str = ""
    output_hash: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "generated_at": self.generated_at,
            "wave_id": self.wave_id,
            "angles_used": self.angles_used,
            "outputs": {
                "hooks": self.hooks_count,
                "scripts_7s": self.scripts_7s_count,
                "scripts_15s": self.scripts_15s_count,
                "scripts_30s": self.scripts_30s_count,
                "primary_texts": self.primary_texts_count,
                "headlines": self.headlines_count,
                "landing_skeletons": self.landing_skeletons_count,
            },
            "quality_score": round(self.quality_score, 3),
            "compliance_flags": self.compliance_flags,
            "interrogation": {
                "verdict": self.interrogation_verdict,
                "score": round(self.interrogation_score, 3),
            },
            "hashes": {
                "input": self.input_hash,
                "output": self.output_hash,
            },
        }


@dataclass
class QualityFilterResult:
    """Resultado del quality filter."""
    passed: bool
    reason: str
    
    # Scores
    total_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    
    # Issues
    issues: List[str] = field(default_factory=list)
    
    # Regeneration
    regeneration_hint: str = ""


# ============================================================
# MARKET PULSE MODELS
# ============================================================

@dataclass
class Signal:
    """Señal de mercado."""
    signal_type: Literal["macro", "micro", "trend", "risk"]
    description: str
    evidence_url: str  # REQUIRED
    source_name: str
    confidence: float
    extracted_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.signal_type,
            "description": self.description,
            "evidence_url": self.evidence_url,
            "source": self.source_name,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class MarketPulseMemo:
    """Memo diario de Market Pulse."""
    date: str
    conclusion: str
    signals: List[Signal]
    implication_trendify: str
    test_idea: str
    overall_confidence: float
    schema_version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "date": self.date,
            "conclusion": self.conclusion,
            "signals": [s.to_dict() for s in self.signals],
            "implication_trendify": self.implication_trendify,
            "test_idea": self.test_idea,
            "confidence": round(self.overall_confidence, 2),
        }
