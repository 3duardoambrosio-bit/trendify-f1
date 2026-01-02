# synapse/marketing_os/experiment_engine.py
"""
Experiment Engine - Stop-loss, scaling, y decision rules.

Protege tu capital con reglas automaticas:
- Stop-loss por CPA/CTR/Hook Rate
- Scaling solo con confianza estadistica
- UTM tracking normalizado
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib


class ExperimentStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    KILLED = "killed"
    SCALED = "scaled"
    GRADUATED = "graduated"


class Decision(Enum):
    CONTINUE = "continue"
    PAUSE = "pause"
    KILL = "kill"
    SCALE_UP = "scale_up"
    GRADUATE = "graduate"


@dataclass
class StopLossConfig:
    """Configuracion de stop-loss."""
    min_spend_usd: float = 15.0
    min_hours: int = 24
    cpa_max_multiplier: float = 2.5
    ctr_min: float = 0.5
    hook_rate_min: float = 10.0
    cvr_min: float = 0.5
    
    # Scaling thresholds
    scale_min_conversions: int = 3
    scale_min_confidence: float = 0.7
    scale_max_cpa_multiplier: float = 1.5
    
    # Graduate thresholds
    graduate_min_conversions: int = 10
    graduate_min_roas: float = 1.5


@dataclass
class ExperimentMetrics:
    """Metricas de un experimento."""
    experiment_id: str
    product_id: str
    variant_id: str
    
    # Spend
    spend_usd: float = 0.0
    hours_running: float = 0.0
    
    # Performance
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    revenue_usd: float = 0.0
    
    # Video metrics
    video_views: int = 0
    video_3s_views: int = 0
    
    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions * 100) if self.impressions > 0 else 0
    
    @property
    def cvr(self) -> float:
        return (self.conversions / self.clicks * 100) if self.clicks > 0 else 0
    
    @property
    def cpa(self) -> float:
        return self.spend_usd / self.conversions if self.conversions > 0 else float("inf")
    
    @property
    def roas(self) -> float:
        return self.revenue_usd / self.spend_usd if self.spend_usd > 0 else 0
    
    @property
    def hook_rate(self) -> float:
        return (self.video_3s_views / self.impressions * 100) if self.impressions > 0 else 0
    
    @property
    def cpm(self) -> float:
        return (self.spend_usd / self.impressions * 1000) if self.impressions > 0 else 0


@dataclass
class ExperimentDecision:
    """Decision sobre un experimento."""
    experiment_id: str
    decision: Decision
    reasons: List[str]
    confidence: float
    recommended_action: str
    metrics_snapshot: Dict[str, float]
    decided_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExperimentEngine:
    """
    Motor de decisiones para experimentos.
    
    Uso:
        engine = ExperimentEngine()
        decision = engine.evaluate(metrics, target_cpa=150)
    """
    
    def __init__(self, config: Optional[StopLossConfig] = None):
        self.config = config or StopLossConfig()
    
    def evaluate(
        self,
        metrics: ExperimentMetrics,
        target_cpa: float,
        target_roas: float = 1.0,
    ) -> ExperimentDecision:
        """
        Evalua metricas y decide accion.
        
        Args:
            metrics: Metricas del experimento
            target_cpa: CPA objetivo en USD
            target_roas: ROAS objetivo
            
        Returns:
            ExperimentDecision con accion recomendada
        """
        reasons = []
        decision = Decision.CONTINUE
        confidence = 0.5
        
        # Check minimum thresholds before judging
        if metrics.spend_usd < self.config.min_spend_usd:
            return ExperimentDecision(
                experiment_id=metrics.experiment_id,
                decision=Decision.CONTINUE,
                reasons=[f"Insufficient spend: ${metrics.spend_usd:.2f} < ${self.config.min_spend_usd}"],
                confidence=0.3,
                recommended_action="Wait for more data",
                metrics_snapshot=self._snapshot(metrics),
            )
        
        if metrics.hours_running < self.config.min_hours:
            return ExperimentDecision(
                experiment_id=metrics.experiment_id,
                decision=Decision.CONTINUE,
                reasons=[f"Insufficient time: {metrics.hours_running:.1f}h < {self.config.min_hours}h"],
                confidence=0.3,
                recommended_action="Wait for more time",
                metrics_snapshot=self._snapshot(metrics),
            )
        
        # === KILL CONDITIONS ===
        max_cpa = target_cpa * self.config.cpa_max_multiplier
        
        if metrics.conversions > 0 and metrics.cpa > max_cpa:
            reasons.append(f"CPA too high: ${metrics.cpa:.2f} > ${max_cpa:.2f}")
            decision = Decision.KILL
            confidence = 0.8
        
        if metrics.ctr < self.config.ctr_min and metrics.impressions > 1000:
            reasons.append(f"CTR too low: {metrics.ctr:.2f}% < {self.config.ctr_min}%")
            decision = Decision.KILL
            confidence = 0.7
        
        if metrics.hook_rate < self.config.hook_rate_min and metrics.impressions > 500:
            reasons.append(f"Hook rate too low: {metrics.hook_rate:.1f}% < {self.config.hook_rate_min}%")
            decision = Decision.KILL
            confidence = 0.7
        
        if metrics.conversions == 0 and metrics.spend_usd > target_cpa * 2:
            reasons.append(f"No conversions after ${metrics.spend_usd:.2f} spend")
            decision = Decision.KILL
            confidence = 0.85
        
        # === SCALE CONDITIONS ===
        if decision == Decision.CONTINUE:
            scale_cpa = target_cpa * self.config.scale_max_cpa_multiplier
            
            if (metrics.conversions >= self.config.scale_min_conversions and
                metrics.cpa <= scale_cpa and
                metrics.ctr >= self.config.ctr_min):
                reasons.append(f"Strong performance: {metrics.conversions} conversions at ${metrics.cpa:.2f} CPA")
                decision = Decision.SCALE_UP
                confidence = 0.7
        
        # === GRADUATE CONDITIONS ===
        if decision in [Decision.CONTINUE, Decision.SCALE_UP]:
            if (metrics.conversions >= self.config.graduate_min_conversions and
                metrics.roas >= self.config.graduate_min_roas and
                metrics.cpa <= target_cpa):
                reasons.append(f"Ready to graduate: {metrics.conversions} conversions, {metrics.roas:.2f}x ROAS")
                decision = Decision.GRADUATE
                confidence = 0.85
        
        # Default continue
        if not reasons:
            reasons.append("Metrics within acceptable range, continue testing")
        
        # Recommended action
        action_map = {
            Decision.CONTINUE: "Keep running, monitor metrics",
            Decision.PAUSE: "Pause and review creative",
            Decision.KILL: "Kill experiment, reallocate budget",
            Decision.SCALE_UP: f"Increase budget 50%, monitor for 24h",
            Decision.GRADUATE: "Move to scaling phase with larger budget",
        }
        
        return ExperimentDecision(
            experiment_id=metrics.experiment_id,
            decision=decision,
            reasons=reasons,
            confidence=confidence,
            recommended_action=action_map[decision],
            metrics_snapshot=self._snapshot(metrics),
        )
    
    def _snapshot(self, metrics: ExperimentMetrics) -> Dict[str, float]:
        return {
            "spend_usd": metrics.spend_usd,
            "impressions": metrics.impressions,
            "clicks": metrics.clicks,
            "conversions": metrics.conversions,
            "ctr": metrics.ctr,
            "cvr": metrics.cvr,
            "cpa": metrics.cpa if metrics.conversions > 0 else 0,
            "roas": metrics.roas,
            "hook_rate": metrics.hook_rate,
        }
    
    def generate_utm(
        self,
        product_id: str,
        hook_id: str,
        angle: str,
        format: str,
        variant: str,
    ) -> Dict[str, str]:
        """
        Genera UTM parameters normalizados.
        
        Returns:
            Dict con utm_source, utm_medium, utm_campaign, utm_content
        """
        return {
            "utm_source": "paid",
            "utm_medium": "social",
            "utm_campaign": f"P{product_id}",
            "utm_content": f"H{hook_id}_A{angle[:3]}_F{format[:4]}_V{variant}",
        }
    
    def batch_evaluate(
        self,
        experiments: List[ExperimentMetrics],
        target_cpa: float,
    ) -> Dict[str, List[ExperimentDecision]]:
        """
        Evalua batch de experimentos y agrupa por decision.
        """
        decisions = [self.evaluate(exp, target_cpa) for exp in experiments]
        
        result = {
            "kill": [],
            "scale": [],
            "graduate": [],
            "continue": [],
        }
        
        for d in decisions:
            if d.decision == Decision.KILL:
                result["kill"].append(d)
            elif d.decision == Decision.SCALE_UP:
                result["scale"].append(d)
            elif d.decision == Decision.GRADUATE:
                result["graduate"].append(d)
            else:
                result["continue"].append(d)
        
        return result


def quick_evaluate(
    spend: float,
    impressions: int,
    clicks: int,
    conversions: int,
    target_cpa: float,
    hours: float = 24,
) -> ExperimentDecision:
    """Helper para evaluacion rapida."""
    metrics = ExperimentMetrics(
        experiment_id="quick",
        product_id="quick",
        variant_id="quick",
        spend_usd=spend,
        hours_running=hours,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
    )
    
    engine = ExperimentEngine()
    return engine.evaluate(metrics, target_cpa)
