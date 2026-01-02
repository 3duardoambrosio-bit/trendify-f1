# synapse/marketing_os/quality_filter.py
"""
Quality Filter - Nivel F1

Filtro dual:
1. Contract Filter: valida estructura, campos, límites
2. Meta Filter: evalúa calidad en 6 dimensiones

Dimensiones:
- clarity: ¿Se entiende en 3 segundos?
- persuasion: ¿Tiene reason-why?
- differentiation: ¿Suena único o genérico?
- compliance: ¿Riesgo de policy?
- mexicanidad: ¿Suena natural en MX?
- actionability: ¿Dice qué hacer?

Reglas:
- ANY score < 0.4 -> REGENERATE
- average < 0.6 -> REGENERATE
- duplicate -> REGENERATE
- max 3 regenerations -> ASK HUMAN
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    ContentType,
    QualityDimension,
    QualityFilterResult,
)


# ============================================================
# CONSTANTS
# ============================================================

CONTENT_LIMITS = {
    ContentType.HOOK: {"min": 10, "max": 100},
    ContentType.SCRIPT_7S: {"min": 20, "max": 150},
    ContentType.SCRIPT_15S: {"min": 40, "max": 300},
    ContentType.SCRIPT_30S: {"min": 80, "max": 600},
    ContentType.PRIMARY_TEXT: {"min": 50, "max": 500},
    ContentType.HEADLINE: {"min": 10, "max": 80},
    ContentType.LANDING: {"min": 200, "max": 2000},
}

GENERIC_PHRASES = [
    "alta calidad", "mejor precio", "increíble", "el mejor", "único",
    "excelente", "premium", "profesional", "innovador", "revolucionario",
    "de primera", "superior", "inigualable", "excepcional", "extraordinario",
    "sorprendente", "maravilloso", "fantástico", "perfecto", "ideal",
]

SPAIN_SPANISH = [
    "vale", "mola", "tío", "vosotros", "guay", "flipar", "currar",
    "quedar", "pillar", "coger el autobús", "móvil", "ordenador",
]

COMPLIANCE_TERMS = [
    "garantizado", "100%", "cura", "trata", "médico", "clínico",
    "fda", "cofepris", "aprobado", "certificado", "científicamente",
    "probado", "resultados", "testimonios", "doctores recomiendan",
]

FILLER_WORDS = [
    "básicamente", "literalmente", "realmente", "sinceramente",
    "honestamente", "obviamente", "claramente", "simplemente",
    "naturalmente", "definitivamente", "absolutamente", "totalmente",
]


# ============================================================
# CONTRACT FILTER
# ============================================================

@dataclass
class ContractValidation:
    """Resultado de validación de contrato."""
    valid: bool
    issues: List[str]


class ContractFilter:
    """
    Filter 1: Validación de contrato.
    
    Verifica:
    - Campos completos (no nulls/empty)
    - Longitud dentro de límites
    - No claims prohibidos
    - Encoding correcto
    - Variables reemplazadas
    """
    
    def __init__(self):
        self.placeholder_pattern = re.compile(r'\{[a-z_]+\}')
    
    def validate(
        self,
        content: str,
        content_type: ContentType,
        required_fields: Optional[Dict[str, Any]] = None,
    ) -> ContractValidation:
        issues = []
        
        if not content or not content.strip():
            issues.append("EMPTY_CONTENT")
            return ContractValidation(valid=False, issues=issues)
        
        content = content.strip()
        
        limits = CONTENT_LIMITS.get(content_type, {"min": 10, "max": 1000})
        if len(content) < limits["min"]:
            issues.append(f"TOO_SHORT: {len(content)} < {limits['min']}")
        if len(content) > limits["max"]:
            issues.append(f"TOO_LONG: {len(content)} > {limits['max']}")
        
        placeholders = self.placeholder_pattern.findall(content)
        if placeholders:
            issues.append(f"UNREPLACED_PLACEHOLDERS: {placeholders}")
        
        if "â€" in content or "Â" in content or "Ã" in content:
            issues.append("ENCODING_ISSUES")
        
        if content.isupper() and len(content) > 20:
            issues.append("ALL_CAPS")
        
        if required_fields:
            for field_name, expected in required_fields.items():
                if expected and field_name not in content.lower():
                    issues.append(f"MISSING_FIELD: {field_name}")
        
        return ContractValidation(
            valid=len(issues) == 0,
            issues=issues,
        )


# ============================================================
# META FILTER (6 DIMENSIONS)
# ============================================================

@dataclass
class DimensionScore:
    """Score de una dimensión."""
    dimension: QualityDimension
    score: float
    reason: str


class MetaFilter:
    """
    Filter 2: Meta-evaluador de calidad.
    
    Evalúa 6 dimensiones y detecta duplicados.
    """
    
    def __init__(self):
        self.seen_hashes: Set[str] = set()
        self.content_history: List[str] = []
    
    def evaluate(
        self,
        content: str,
        content_type: ContentType,
    ) -> Tuple[bool, Dict[str, float], List[str]]:
        """
        Evalúa contenido.
        
        Returns:
            (passed, dimension_scores, issues)
        """
        issues = []
        
        content_hash = hashlib.md5(content.lower().encode()).hexdigest()
        if content_hash in self.seen_hashes:
            return False, {}, ["DUPLICATE"]
        
        if self._is_too_similar(content):
            return False, {}, ["TOO_SIMILAR_TO_PREVIOUS"]
        
        scores = {
            QualityDimension.CLARITY.value: self._score_clarity(content),
            QualityDimension.PERSUASION.value: self._score_persuasion(content),
            QualityDimension.DIFFERENTIATION.value: self._score_differentiation(content),
            QualityDimension.COMPLIANCE.value: self._score_compliance(content),
            QualityDimension.MEXICANIDAD.value: self._score_mexicanidad(content),
            QualityDimension.ACTIONABILITY.value: self._score_actionability(content, content_type),
        }
        
        min_score = min(scores.values())
        avg_score = sum(scores.values()) / len(scores)
        
        if min_score < 0.4:
            worst = min(scores, key=scores.get)
            issues.append(f"LOW_SCORE_{worst.upper()}")
        
        if avg_score < 0.6:
            issues.append(f"AVERAGE_TOO_LOW: {avg_score:.2f}")
        
        passed = len(issues) == 0
        
        if passed:
            self.seen_hashes.add(content_hash)
            self.content_history.append(content)
        
        return passed, scores, issues
    
    def _is_too_similar(self, content: str, threshold: float = 0.8) -> bool:
        """Check si es muy similar a contenido previo."""
        content_words = set(content.lower().split())
        
        for prev in self.content_history[-20:]:
            prev_words = set(prev.lower().split())
            if not prev_words:
                continue
            
            intersection = len(content_words & prev_words)
            union = len(content_words | prev_words)
            
            if union > 0 and intersection / union > threshold:
                return True
        
        return False
    
    def _score_clarity(self, content: str) -> float:
        """Evalúa claridad."""
        score = 1.0
        
        sentences = content.split('.')
        avg_words_per_sentence = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        if avg_words_per_sentence > 25:
            score -= 0.3
        elif avg_words_per_sentence > 20:
            score -= 0.15
        
        content_lower = content.lower()
        filler_count = sum(1 for f in FILLER_WORDS if f in content_lower)
        score -= filler_count * 0.1
        
        tech_words = ["coadyuvar", "mediante", "asimismo", "subsecuente", "implementar"]
        tech_count = sum(1 for t in tech_words if t in content_lower)
        score -= tech_count * 0.15
        
        return max(0.1, min(1.0, score))
    
    def _score_persuasion(self, content: str) -> float:
        """Evalúa persuasión."""
        score = 0.5
        
        content_lower = content.lower()
        
        reason_indicators = ["porque", "por eso", "gracias a", "ya que", "debido a"]
        if any(r in content_lower for r in reason_indicators):
            score += 0.2
        
        benefit_words = ["ahorra", "gana", "evita", "protege", "mejora", "obtén", "disfruta"]
        benefits = sum(1 for b in benefit_words if b in content_lower)
        score += min(benefits * 0.1, 0.2)
        
        if re.search(r'\d+', content):
            score += 0.1
        
        urgency = ["hoy", "ahora", "última", "limitado"]
        if any(u in content_lower for u in urgency):
            score += 0.1
        
        return max(0.1, min(1.0, score))
    
    def _score_differentiation(self, content: str) -> float:
        """Evalúa diferenciación."""
        score = 0.8
        
        content_lower = content.lower()
        
        generic_count = sum(1 for g in GENERIC_PHRASES if g in content_lower)
        score -= generic_count * 0.15
        
        if re.search(r'\d+%|\d+ horas|\d+ días|\$\d+', content):
            score += 0.15
        
        comparison_words = ["vs", "comparado", "a diferencia", "mientras que"]
        if any(c in content_lower for c in comparison_words):
            score += 0.1
        
        return max(0.1, min(1.0, score))
    
    def _score_compliance(self, content: str) -> float:
        """Evalúa compliance (riesgo de policy)."""
        score = 1.0
        
        content_lower = content.lower()
        
        for term in COMPLIANCE_TERMS:
            if term.lower() in content_lower:
                score -= 0.2
        
        absolute_claims = ["siempre", "nunca", "todos", "nadie", "jamás"]
        for claim in absolute_claims:
            if claim in content_lower:
                score -= 0.1
        
        return max(0.1, min(1.0, score))
    
    def _score_mexicanidad(self, content: str) -> float:
        """Evalúa si suena natural en México."""
        score = 0.9
        
        content_lower = content.lower()
        
        for term in SPAIN_SPANISH:
            if term in content_lower:
                score -= 0.2
        
        mx_words = ["chido", "padre", "neta", "onda", "órale", "chance"]
        mx_count = sum(1 for m in mx_words if m in content_lower)
        if mx_count == 1:
            score += 0.1
        elif mx_count > 2:
            score -= 0.1
        
        return max(0.1, min(1.0, score))
    
    def _score_actionability(self, content: str, content_type: ContentType) -> float:
        """Evalúa si dice qué hacer."""
        score = 0.5
        
        content_lower = content.lower()
        
        cta_words = {
            ContentType.HOOK: ["descubre", "mira", "conoce", "entérate"],
            ContentType.HEADLINE: ["compra", "obtén", "prueba", "aprovecha"],
            ContentType.PRIMARY_TEXT: ["haz clic", "visita", "compra ahora", "añade"],
            ContentType.LANDING: ["agregar", "comprar", "ordenar", "enviar"],
        }
        
        expected_ctas = cta_words.get(content_type, [])
        
        for cta in expected_ctas:
            if cta in content_lower:
                score += 0.2
                break
        
        imperatives = ["descubre", "prueba", "experimenta", "transforma", "mejora"]
        if any(imp in content_lower for imp in imperatives):
            score += 0.15
        
        if content_type in [ContentType.SCRIPT_7S, ContentType.SCRIPT_15S, ContentType.SCRIPT_30S]:
            score = max(score, 0.6)
        
        return max(0.1, min(1.0, score))
    
    def reset(self):
        """Reset state (para nuevo batch)."""
        self.seen_hashes.clear()
        self.content_history.clear()


# ============================================================
# COMBINED QUALITY FILTER
# ============================================================

class QualityFilter:
    """
    Filtro combinado de calidad.
    
    Uso:
        filter = QualityFilter()
        result = filter.check(content, ContentType.HOOK)
        
        if result.passed:
            # Contenido aprobado
        else:
            # result.issues tiene los problemas
            # result.regeneration_hint dice qué mejorar
    """
    
    def __init__(self, max_regenerations: int = 3):
        self.contract_filter = ContractFilter()
        self.meta_filter = MetaFilter()
        self.max_regenerations = max_regenerations
        self.regeneration_counts: Dict[str, int] = {}
    
    def check(
        self,
        content: str,
        content_type: ContentType,
        content_id: Optional[str] = None,
    ) -> QualityFilterResult:
        """
        Verifica contenido contra ambos filtros.
        
        Args:
            content: Contenido a verificar
            content_type: Tipo de contenido
            content_id: ID para tracking de regeneraciones
            
        Returns:
            QualityFilterResult
        """
        all_issues = []
        
        contract_result = self.contract_filter.validate(content, content_type)
        if not contract_result.valid:
            all_issues.extend(contract_result.issues)
        
        dimension_scores = {}
        if contract_result.valid:
            passed, scores, meta_issues = self.meta_filter.evaluate(content, content_type)
            dimension_scores = scores
            all_issues.extend(meta_issues)
        
        total_score = sum(dimension_scores.values()) / len(dimension_scores) if dimension_scores else 0.0
        
        if content_id:
            self.regeneration_counts[content_id] = self.regeneration_counts.get(content_id, 0)
            if all_issues:
                self.regeneration_counts[content_id] += 1
            
            if self.regeneration_counts[content_id] >= self.max_regenerations:
                all_issues.append("MAX_REGENERATIONS_REACHED")
        
        hint = self._generate_hint(all_issues, dimension_scores)
        
        return QualityFilterResult(
            passed=len(all_issues) == 0,
            reason="APPROVED" if len(all_issues) == 0 else all_issues[0],
            total_score=total_score,
            dimension_scores=dimension_scores,
            issues=all_issues,
            regeneration_hint=hint,
        )
    
    def _generate_hint(
        self,
        issues: List[str],
        scores: Dict[str, float]
    ) -> str:
        """Genera hint para regeneración."""
        if not issues:
            return ""
        
        hints = []
        
        for issue in issues:
            if "CLARITY" in issue:
                hints.append("Simplificar: oraciones más cortas, menos jerga")
            elif "PERSUASION" in issue:
                hints.append("Agregar 'porque' o beneficio concreto")
            elif "DIFFERENTIATION" in issue:
                hints.append("Evitar frases genéricas, agregar números específicos")
            elif "COMPLIANCE" in issue:
                hints.append("Eliminar claims absolutos o médicos")
            elif "MEXICANIDAD" in issue:
                hints.append("Usar español mexicano natural")
            elif "ACTIONABILITY" in issue:
                hints.append("Agregar verbo imperativo o CTA")
            elif "DUPLICATE" in issue:
                hints.append("Variar estructura y palabras clave")
            elif "TOO_SHORT" in issue:
                hints.append("Expandir con más detalles")
            elif "TOO_LONG" in issue:
                hints.append("Recortar a lo esencial")
            elif "MAX_REGENERATIONS" in issue:
                hints.append("REQUIERE INPUT HUMANO - máximo de intentos alcanzado")
        
        return "; ".join(hints[:3])
    
    def reset(self):
        """Reset state."""
        self.meta_filter.reset()
        self.regeneration_counts.clear()


# ============================================================
# HELPERS
# ============================================================

def quick_check(content: str, content_type: ContentType) -> bool:
    """Check rápido sin tracking."""
    filter = QualityFilter()
    result = filter.check(content, content_type)
    return result.passed
