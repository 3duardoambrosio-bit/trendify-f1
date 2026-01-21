# synapse/discovery/product_ranker.py
"""
Product Ranker - Scoring multi-dimensional para ranking de productos.

Combina: margin, probability_success, differentiation, demand_signals.
Output: Top N productos listos para marketing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import json
import math
from pathlib import Path

from .catalog_scanner import ProductCandidate


@dataclass
class ProductScore:
    """Score multi-dimensional de un producto."""
    product_id: str
    title: str
    
    # Scores individuales (0-1)
    margin_score: float = 0.0
    demand_score: float = 0.0
    quality_score: float = 0.0
    differentiation_score: float = 0.0
    risk_score: float = 0.0  # Inverso: alto = menos riesgo
    
    # Score compuesto
    total_score: float = 0.0
    rank: int = 0
    
    # Metadata
    margin_percent: float = 0.0
    price: float = 0.0
    
    # Reasoning
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class RankingResult:
    """Resultado de ranking."""
    niche_id: str
    ranked_at: str
    total_evaluated: int
    
    # Config
    weights: Dict[str, float] = field(default_factory=dict)
    
    # Results
    ranked_products: List[ProductScore] = field(default_factory=list)
    
    # Stats
    avg_score: float = 0.0
    score_distribution: Dict[str, int] = field(default_factory=dict)


class ProductRanker:
    """
    Rankea productos usando scoring multi-dimensional.
    
    Uso:
        ranker = ProductRanker()
        result = ranker.rank(candidates, top_n=10)
    """
    
    DEFAULT_WEIGHTS = {
        "margin": 0.30,
        "demand": 0.25,
        "quality": 0.20,
        "differentiation": 0.15,
        "risk": 0.10,
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
    
    def rank(
        self,
        candidates: List[ProductCandidate],
        top_n: int = 10,
        min_score: float = 0.4,
    ) -> RankingResult:
        """
        Rankea productos y retorna top N.
        """
        scored = []
        
        for candidate in candidates:
            score = self._score_product(candidate)
            if score.total_score >= min_score:
                scored.append(score)
        
        # Sort by total_score descending
        scored.sort(key=lambda x: x.total_score, reverse=True)
        
        # Assign ranks
        for i, s in enumerate(scored):
            s.rank = i + 1
        
        # Take top N
        top = scored[:top_n]
        
        # Calculate stats
        avg_score = sum(s.total_score for s in top) / len(top) if top else 0
        distribution = self._calculate_distribution(scored)
        
        return RankingResult(
            niche_id="",
            ranked_at=datetime.now(timezone.utc).isoformat(),
            total_evaluated=len(candidates),
            weights=self.weights,
            ranked_products=top,
            avg_score=avg_score,
            score_distribution=distribution,
        )
    
    def _score_product(self, p: ProductCandidate) -> ProductScore:
        """Calcula scores para un producto."""
        
        # 1. Margin Score (0-1)
        # 70%+ margin = 1.0, 40% = 0.5, <30% = 0.2
        margin_score = min(1.0, max(0, (p.margin_percent - 30) / 40))
        
        # 2. Demand Score (0-1) based on reviews/sales
        # More reviews = higher demand signal
        reviews_score = min(1.0, p.reviews / 200) if p.reviews > 0 else 0.3
        sales_score = min(1.0, p.sales / 500) if p.sales > 0 else 0.3
        demand_score = (reviews_score * 0.6 + sales_score * 0.4)
        
        # 3. Quality Score (0-1) based on rating
        if p.rating >= 4.5:
            quality_score = 1.0
        elif p.rating >= 4.0:
            quality_score = 0.8
        elif p.rating >= 3.5:
            quality_score = 0.6
        elif p.rating > 0:
            quality_score = 0.4
        else:
            quality_score = 0.5  # Unknown
        
        # 4. Differentiation Score (0-1) based on keyword matches
        differentiation_score = min(1.0, p.match_score * 1.5)
        
        # 5. Risk Score (0-1) - higher = less risky
        risk_factors = 0
        if p.shipping_days > 10:
            risk_factors += 1
        if p.images_count < 3:
            risk_factors += 1
        if p.rating > 0 and p.rating < 4.0:
            risk_factors += 1
        if p.reviews < 20:
            risk_factors += 1
        risk_score = max(0, 1.0 - (risk_factors * 0.25))
        
        # Calculate total score
        total_score = (
            margin_score * self.weights["margin"] +
            demand_score * self.weights["demand"] +
            quality_score * self.weights["quality"] +
            differentiation_score * self.weights["differentiation"] +
            risk_score * self.weights["risk"]
        )
        
        # Generate strengths/weaknesses
        strengths = []
        weaknesses = []
        
        if margin_score >= 0.7:
            strengths.append(f"Alto margen ({p.margin_percent:.0f}%)")
        elif margin_score < 0.4:
            weaknesses.append(f"Margen bajo ({p.margin_percent:.0f}%)")
        
        if demand_score >= 0.6:
            strengths.append(f"Buena demanda ({p.reviews} reviews)")
        elif demand_score < 0.3:
            weaknesses.append("Poca evidencia de demanda")
        
        if quality_score >= 0.8:
            strengths.append(f"Alta calidad ({p.rating} estrellas)")
        elif quality_score < 0.5:
            weaknesses.append(f"Rating bajo ({p.rating})")
        
        if risk_score < 0.5:
            weaknesses.append("Factores de riesgo elevados")
        
        # Recommendation
        if total_score >= 0.7:
            recommendation = "FUERTE CANDIDATO - Priorizar para marketing"
        elif total_score >= 0.5:
            recommendation = "BUEN CANDIDATO - Considerar para tests"
        else:
            recommendation = "EVALUAR - Revisar debilidades antes de proceder"
        
        return ProductScore(
            product_id=p.product_id,
            title=p.title,
            margin_score=margin_score,
            demand_score=demand_score,
            quality_score=quality_score,
            differentiation_score=differentiation_score,
            risk_score=risk_score,
            total_score=total_score,
            margin_percent=p.margin_percent,
            price=p.price,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendation=recommendation,
        )
    
    def _calculate_distribution(self, scored: List[ProductScore]) -> Dict[str, int]:
        """Calcula distribucion de scores."""
        distribution = {
            "excellent": 0,  # >= 0.7
            "good": 0,       # >= 0.5
            "fair": 0,       # >= 0.4
            "poor": 0,       # < 0.4
        }
        
        for s in scored:
            if s.total_score >= 0.7:
                distribution["excellent"] += 1
            elif s.total_score >= 0.5:
                distribution["good"] += 1
            elif s.total_score >= 0.4:
                distribution["fair"] += 1
            else:
                distribution["poor"] += 1
        
        return distribution


def rank_products(candidates: List[ProductCandidate], top_n: int = 10) -> List[ProductScore]:
    """Helper para ranking rapido."""
    ranker = ProductRanker()
    result = ranker.rank(candidates, top_n=top_n)
    return result.ranked_products
