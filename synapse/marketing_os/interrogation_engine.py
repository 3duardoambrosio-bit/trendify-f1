# synapse/marketing_os/interrogation_engine.py
"""
Interrogation Engine - Nivel F1

Motor de cuestionamiento pre-lanzamiento.
No gasta $1 sin análisis.

Frameworks:
- JTBD (Jobs To Be Done)
- Emotion Map (emoción, enemigo, miedos)
- Objection Analysis
- Compliance Check
- Differentiation

Verdicts:
- BLOCK: no gastar $1 (compliance crítico, sin respuesta a objeción, score < 0.4)
- NEEDS_WORK: revisar (0.4-0.6)
- LAUNCH: procede (>0.6 y blocking frameworks pasan)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ProductContext,
    InterrogationResult,
    InterrogationVerdict,
    Emotion,
    Angle,
    Risk,
)


# ============================================================
# FRAMEWORK RESULTS
# ============================================================

@dataclass
class FrameworkResult:
    """Resultado de un framework individual."""
    name: str
    score: float
    findings: Dict[str, Any]
    passed: bool
    blocking: bool = False
    blocking_reason: Optional[str] = None


# ============================================================
# COMPLIANCE DATA
# ============================================================

COMPLIANCE_TERMS = {
    "medical": [
        "cura", "trata", "sana", "medicina", "medicinal", "terapéutico",
        "clínico", "doctor", "médico", "enfermedad", "síntoma", "diagnóstico",
        "fda", "cofepris", "aprobado médicamente",
    ],
    "health_claims": [
        "baja de peso", "adelgaza", "quema grasa", "metabolismo",
        "colesterol", "diabetes", "presión arterial", "cáncer",
        "artritis", "insomnio", "ansiedad", "depresión",
    ],
    "guarantees": [
        "garantizado", "100% efectivo", "resultados garantizados",
        "funciona siempre", "sin fallas", "perfecto",
    ],
    "exaggerations": [
        "el mejor del mundo", "único en el mercado", "revolucionario",
        "milagroso", "increíble", "nunca antes visto", "el #1",
    ],
    "certifications": [
        "certificado", "aprobado por", "recomendado por doctores",
        "clínicamente probado", "científicamente comprobado",
    ],
}

CATEGORY_RISKS = {
    "electronics": ["batería", "voltaje", "sobrecalentamiento"],
    "beauty": ["alérgenos", "ingredientes", "piel sensible"],
    "supplements": ["efectos secundarios", "contraindicaciones"],
    "children": ["seguridad infantil", "partes pequeñas", "certificación"],
    "food": ["alérgenos", "caducidad", "ingredientes"],
}


# ============================================================
# CATEGORY MAPPINGS
# ============================================================

CATEGORY_EMOTIONS = {
    "electronics": [Emotion.CONTROL, Emotion.STATUS],
    "audio": [Emotion.PLEASURE, Emotion.CONTROL],
    "fitness": [Emotion.CONTROL, Emotion.STATUS],
    "beauty": [Emotion.STATUS, Emotion.SECURITY],
    "fashion": [Emotion.STATUS, Emotion.BELONGING],
    "home": [Emotion.SECURITY, Emotion.CONTROL],
    "kids": [Emotion.SECURITY, Emotion.BELONGING],
}

CATEGORY_ENEMIES = {
    "electronics": "la frustración de que no funcione",
    "audio": "cables enredados y batería muerta",
    "fitness": "la pereza y falta de tiempo",
    "beauty": "verse mal o insegura",
    "fashion": "no encajar o verse anticuado",
    "home": "el desorden y la incomodidad",
}

CATEGORY_JOBS = {
    "electronics": "resolver tareas sin fricción tecnológica",
    "audio": "disfrutar audio sin interrupciones ni incomodidad",
    "fitness": "mantenerme activo de forma práctica",
    "beauty": "verme y sentirme mejor cada día",
    "fashion": "expresar mi estilo y pertenecer",
    "home": "tener un espacio organizado y cómodo",
}

CATEGORY_OBJECTIONS = {
    "electronics": [
        ("calidad", "¿Durará o se descompone en 2 meses?"),
        ("compatibilidad", "¿Funciona con mi dispositivo?"),
        ("garantía", "¿Qué pasa si falla?"),
    ],
    "audio": [
        ("sonido", "¿Se escucha bien o culero?"),
        ("batería", "¿Cuánto dura la batería realmente?"),
        ("comodidad", "¿Me lastima después de usarlos mucho?"),
    ],
    "fitness": [
        ("efectividad", "¿Realmente funciona?"),
        ("dificultad", "¿Es muy difícil de usar?"),
        ("espacio", "¿Ocupa mucho lugar?"),
    ],
    "beauty": [
        ("ingredientes", "¿Tiene químicos dañinos?"),
        ("piel", "¿Es bueno para mi tipo de piel?"),
        ("resultados", "¿En cuánto tiempo veo resultados?"),
    ],
}


# ============================================================
# FRAMEWORK EVALUATORS
# ============================================================

class JTBDEvaluator:
    """Jobs To Be Done framework."""
    
    def evaluate(self, ctx: ProductContext) -> FrameworkResult:
        findings = {}
        score = 0.0
        
        job = self._infer_job(ctx)
        findings["job"] = job
        if job and "no identificado" not in job.lower():
            score += 0.4
        
        alternatives = self._infer_alternatives(ctx)
        findings["alternatives"] = alternatives
        if alternatives:
            score += 0.3
        
        trigger = self._infer_trigger(ctx)
        findings["trigger"] = trigger
        if trigger:
            score += 0.3
        
        return FrameworkResult(
            name="jtbd",
            score=min(1.0, score),
            findings=findings,
            passed=score >= 0.5,
        )
    
    def _infer_job(self, ctx: ProductContext) -> str:
        cat_lower = ctx.category.lower()
        for cat, job in CATEGORY_JOBS.items():
            if cat in cat_lower:
                return f"Contrátame para {job}"
        
        name_lower = ctx.name.lower()
        if any(w in name_lower for w in ["audífono", "auricular", "earbuds", "headphone"]):
            return "Contrátame para escuchar audio sin cables ni molestias"
        if any(w in name_lower for w in ["reloj", "watch", "smartwatch"]):
            return "Contrátame para monitorear mi día sin sacar el celular"
        if any(w in name_lower for w in ["lámpara", "luz", "light"]):
            return "Contrátame para iluminar mi espacio con estilo"
        
        if ctx.use_cases:
            return f"Contrátame para {ctx.use_cases[0]}"
        
        return "Job no identificado claramente"
    
    def _infer_alternatives(self, ctx: ProductContext) -> List[str]:
        cat_lower = ctx.category.lower()
        
        alternatives = {
            "audio": ["audífonos con cable", "bocina bluetooth", "no escuchar música"],
            "electronics": ["producto de marca cara", "solución manual", "no hacer nada"],
            "fitness": ["gym tradicional", "ejercicio sin equipo", "no hacer ejercicio"],
            "beauty": ["productos de farmacia", "tratamientos profesionales", "no hacer nada"],
        }
        
        for cat, alts in alternatives.items():
            if cat in cat_lower:
                return alts
        
        return ["producto de marca establecida", "solución manual", "no comprar nada"]
    
    def _infer_trigger(self, ctx: ProductContext) -> str:
        cat_lower = ctx.category.lower()
        
        triggers = {
            "audio": "Cuando mis audífonos actuales fallan o me frustran",
            "electronics": "Cuando necesito resolver algo y no tengo herramienta",
            "fitness": "Cuando decido ponerme en forma (Año Nuevo, evento, etc)",
            "beauty": "Cuando tengo evento importante o me siento insegura",
        }
        
        for cat, trigger in triggers.items():
            if cat in cat_lower:
                return trigger
        
        return "Momento de necesidad o impulso de mejora"


class EmotionMapEvaluator:
    """Mapa emocional framework."""
    
    def evaluate(self, ctx: ProductContext) -> FrameworkResult:
        findings = {}
        score = 0.0
        
        primary, secondary = self._infer_emotions(ctx)
        findings["emotion_primary"] = primary.value if primary else None
        findings["emotion_secondary"] = secondary.value if secondary else None
        if primary:
            score += 0.4
        
        enemy = self._infer_enemy(ctx)
        findings["enemy"] = enemy
        if enemy and len(enemy) > 5:
            score += 0.3
        
        fears = self._infer_fears(ctx)
        findings["fears"] = fears
        if fears:
            score += 0.3
        
        return FrameworkResult(
            name="emotion_map",
            score=min(1.0, score),
            findings=findings,
            passed=score >= 0.5,
            blocking=True,
            blocking_reason="Sin emoción/enemigo claro" if score < 0.5 else None,
        )
    
    def _infer_emotions(self, ctx: ProductContext) -> Tuple[Optional[Emotion], Optional[Emotion]]:
        cat_lower = ctx.category.lower()
        
        for cat, emotions in CATEGORY_EMOTIONS.items():
            if cat in cat_lower:
                return emotions[0], emotions[1] if len(emotions) > 1 else None
        
        if ctx.price > 1000:
            return Emotion.STATUS, Emotion.CONTROL
        elif ctx.price > 500:
            return Emotion.CONTROL, Emotion.PLEASURE
        else:
            return Emotion.RELIEF, None
    
    def _infer_enemy(self, ctx: ProductContext) -> str:
        cat_lower = ctx.category.lower()
        
        for cat, enemy in CATEGORY_ENEMIES.items():
            if cat in cat_lower:
                return enemy
        
        name_lower = ctx.name.lower()
        if any(w in name_lower for w in ["bluetooth", "wireless", "inalámbrico"]):
            return "cables enredados y restricción de movimiento"
        
        return "la frustración de no tener la solución correcta"
    
    def _infer_fears(self, ctx: ProductContext) -> List[str]:
        fears = []
        
        if ctx.margin < 0.3:
            fears.append("precio demasiado alto")
        
        if "china" in ctx.description.lower() or "genérico" in ctx.description.lower():
            fears.append("baja calidad")
        
        fears.extend([
            "que no funcione como esperaba",
            "que se descomponga rápido",
            "que no valga lo que pagué",
        ])
        
        return fears[:3]


class ObjectionEvaluator:
    """Análisis de objeciones framework."""
    
    def evaluate(self, ctx: ProductContext) -> FrameworkResult:
        findings = {}
        score = 0.0
        
        killing_objection, response = self._identify_killing_objection(ctx)
        findings["killing_objection"] = killing_objection
        findings["objection_response"] = response
        
        if killing_objection and len(killing_objection) > 5:
            score += 0.3
        
        if response and len(response) > 10:
            score += 0.4
        
        has_evidence = self._has_evidence(ctx, response)
        findings["has_evidence"] = has_evidence
        if has_evidence:
            score += 0.3
        
        blocking = not response or len(response) < 10
        
        return FrameworkResult(
            name="objection_analysis",
            score=min(1.0, score),
            findings=findings,
            passed=score >= 0.5,
            blocking=blocking,
            blocking_reason="Sin respuesta a objeción principal" if blocking else None,
        )
    
    def _identify_killing_objection(self, ctx: ProductContext) -> Tuple[str, str]:
        cat_lower = ctx.category.lower()
        
        for cat, objections in CATEGORY_OBJECTIONS.items():
            if cat in cat_lower:
                obj_type, obj_text = objections[0]
                response = self._generate_response(obj_type, ctx)
                return obj_text, response
        
        return "¿Vale lo que cuesta?", f"Con {ctx.margin_pct:.0f}% de margen, ofrecemos calidad a precio justo"
    
    def _generate_response(self, obj_type: str, ctx: ProductContext) -> str:
        responses = {
            "calidad": f"Garantía incluida + {ctx.margin_pct:.0f}% margen para soporte",
            "sonido": "Drivers de alta definición con cancelación de ruido",
            "batería": "Hasta 20+ horas con estuche de carga",
            "comodidad": "Diseño ergonómico probado en uso prolongado",
            "compatibilidad": "Compatible con iOS, Android, Windows y más",
            "garantía": "30 días de garantía de satisfacción",
        }
        
        return responses.get(obj_type, "Calidad probada con garantía de satisfacción")
    
    def _has_evidence(self, ctx: ProductContext, response: str) -> bool:
        if not response:
            return False
        
        evidence_patterns = [
            r'\d+%',
            r'\d+ horas',
            r'\d+ días',
            r'garantía',
            r'certificad',
        ]
        
        for pattern in evidence_patterns:
            if re.search(pattern, response.lower()):
                return True
        
        return False


class ComplianceEvaluator:
    """Compliance check framework."""
    
    def evaluate(self, ctx: ProductContext) -> FrameworkResult:
        findings = {}
        flags = []
        score = 1.0
        
        text_to_scan = f"{ctx.name} {ctx.description}".lower()
        
        for category, terms in COMPLIANCE_TERMS.items():
            for term in terms:
                if term.lower() in text_to_scan:
                    flags.append(f"{category}: '{term}'")
                    score -= 0.15
        
        findings["compliance_flags"] = flags
        
        cat_risks = []
        cat_lower = ctx.category.lower()
        for cat, risks in CATEGORY_RISKS.items():
            if cat in cat_lower:
                cat_risks = risks
                break
        
        findings["category_risks"] = cat_risks
        
        critical = any(c.startswith("medical") or c.startswith("health") for c in flags)
        findings["is_critical"] = critical
        
        if critical:
            score = 0.0
        
        score = max(0.0, score)
        
        return FrameworkResult(
            name="compliance",
            score=score,
            findings=findings,
            passed=score >= 0.6,
            blocking=critical,
            blocking_reason="Compliance crítico: claims médicos/salud detectados" if critical else None,
        )


class DifferentiationEvaluator:
    """Diferenciación framework."""
    
    def evaluate(self, ctx: ProductContext) -> FrameworkResult:
        findings = {}
        score = 0.0
        
        unique = ctx.unique_features or self._infer_unique_features(ctx)
        findings["unique_features"] = unique
        if unique:
            score += 0.4
        
        defensible, reason = self._assess_defensibility(ctx, unique)
        findings["is_defensible"] = defensible
        findings["defensibility_reason"] = reason
        if defensible:
            score += 0.3
        
        differentiation = self._generate_differentiation(ctx, unique)
        findings["differentiation"] = differentiation
        if differentiation and "genérico" not in differentiation.lower():
            score += 0.3
        
        return FrameworkResult(
            name="differentiation",
            score=min(1.0, score),
            findings=findings,
            passed=score >= 0.4,
        )
    
    def _infer_unique_features(self, ctx: ProductContext) -> List[str]:
        features = []
        
        name_lower = ctx.name.lower()
        desc_lower = ctx.description.lower()
        
        feature_keywords = {
            "bluetooth 5": "Bluetooth 5.0 (mejor conexión)",
            "cancelación": "Cancelación de ruido",
            "resistente al agua": "Resistente al agua",
            "ipx": "Certificación IPX",
            "carga rápida": "Carga rápida",
            "usb-c": "Puerto USB-C",
            "touch": "Controles táctiles",
        }
        
        for keyword, feature in feature_keywords.items():
            if keyword in name_lower or keyword in desc_lower:
                features.append(feature)
        
        if ctx.price > 800:
            features.append("Calidad premium")
        elif ctx.price < 300:
            features.append("Mejor relación precio-calidad")
        
        return features[:4]
    
    def _assess_defensibility(self, ctx: ProductContext, features: List[str]) -> Tuple[bool, str]:
        if not features:
            return False, "Sin features únicas identificadas"
        
        weak_features = ["bluetooth", "inalámbrico", "portátil", "ligero"]
        strong_features = ["cancelación", "ipx", "certificación", "patente", "garantía extendida"]
        
        has_strong = any(
            any(sf in f.lower() for sf in strong_features)
            for f in features
        )
        
        if has_strong:
            return True, "Tiene features difíciles de copiar"
        
        if ctx.margin > 0.4:
            return True, "Margen permite diferenciación por servicio/garantía"
        
        return False, "Features fácilmente copiables, necesita ángulo único"
    
    def _generate_differentiation(self, ctx: ProductContext, features: List[str]) -> str:
        if features:
            return f"Nos diferenciamos por: {', '.join(features[:3])}"
        
        if ctx.margin > 0.5:
            return "Diferenciación por garantía extendida y soporte premium"
        
        return "Diferenciación genérica - necesita bundle o ángulo único"


# ============================================================
# MAIN ENGINE
# ============================================================

class InterrogationEngine:
    """
    Motor principal de interrogación.
    
    Uso:
        engine = InterrogationEngine()
        result = engine.interrogate(product_context)
        
        if result.passed:
            # Puede lanzar
        else:
            # Revisar blocking_reasons
    """
    
    def __init__(self):
        self.evaluators = [
            JTBDEvaluator(),
            EmotionMapEvaluator(),
            ObjectionEvaluator(),
            ComplianceEvaluator(),
            DifferentiationEvaluator(),
        ]
        
        self.weights = {
            "jtbd": 0.15,
            "emotion_map": 0.25,
            "objection_analysis": 0.25,
            "compliance": 0.20,
            "differentiation": 0.15,
        }
    
    def interrogate(self, ctx: ProductContext) -> InterrogationResult:
        """Ejecuta interrogación completa."""
        
        framework_results: Dict[str, FrameworkResult] = {}
        for evaluator in self.evaluators:
            result = evaluator.evaluate(ctx)
            framework_results[result.name] = result
        
        framework_scores = {name: r.score for name, r in framework_results.items()}
        total_score = sum(
            framework_scores.get(name, 0) * weight
            for name, weight in self.weights.items()
        )
        
        jtbd = framework_results["jtbd"]
        emotion = framework_results["emotion_map"]
        objection = framework_results["objection_analysis"]
        compliance = framework_results["compliance"]
        diff = framework_results["differentiation"]
        
        blocking_reasons = []
        for name, result in framework_results.items():
            if result.blocking and result.blocking_reason:
                blocking_reasons.append(result.blocking_reason)
        
        if blocking_reasons or total_score < 0.4:
            verdict = InterrogationVerdict.BLOCK
        elif total_score < 0.6:
            verdict = InterrogationVerdict.NEEDS_WORK
        else:
            verdict = InterrogationVerdict.LAUNCH
        
        risks = self._compile_risks(ctx, framework_results)
        recommended_angle = self._recommend_angle(emotion, diff)
        recommendations = self._generate_recommendations(ctx, framework_results, verdict)
        
        return InterrogationResult(
            product_id=ctx.product_id,
            product_name=ctx.name,
            total_score=total_score,
            framework_scores=framework_scores,
            emotion_primary=Emotion(emotion.findings.get("emotion_primary")) if emotion.findings.get("emotion_primary") else None,
            emotion_secondary=Emotion(emotion.findings.get("emotion_secondary")) if emotion.findings.get("emotion_secondary") else None,
            enemy=emotion.findings.get("enemy", ""),
            job_to_be_done=jtbd.findings.get("job", ""),
            killing_objection=objection.findings.get("killing_objection", ""),
            objection_response=objection.findings.get("objection_response", ""),
            differentiation=diff.findings.get("differentiation", ""),
            recommended_angle=recommended_angle,
            angles_to_avoid=self._angles_to_avoid(emotion),
            risks=risks,
            compliance_flags=compliance.findings.get("compliance_flags", []),
            verdict=verdict,
            blocking_reasons=blocking_reasons,
            recommendations=recommendations,
            input_hash=ctx.input_hash(),
        )
    
    def _compile_risks(self, ctx: ProductContext, results: Dict[str, FrameworkResult]) -> List[Risk]:
        risks = []
        
        compliance = results["compliance"]
        if compliance.findings.get("compliance_flags"):
            risks.append(Risk(
                description="Claims potencialmente problemáticos detectados",
                severity="high" if compliance.findings.get("is_critical") else "medium",
                mitigation="Revisar y eliminar claims antes de lanzar ads",
                category="compliance",
            ))
        
        diff = results["differentiation"]
        if not diff.findings.get("is_defensible"):
            risks.append(Risk(
                description="Diferenciación débil - competencia puede copiar fácil",
                severity="medium",
                mitigation="Agregar bundle, garantía extendida, o ángulo único",
                category="competition",
            ))
        
        if ctx.margin < 0.35:
            risks.append(Risk(
                description=f"Margen bajo ({ctx.margin_pct:.0f}%) - poco espacio para ads",
                severity="high",
                mitigation="Negociar mejor precio o subir precio de venta",
                category="economics",
            ))
        
        return risks
    
    def _recommend_angle(self, emotion: FrameworkResult, diff: FrameworkResult) -> Angle:
        primary_emotion = emotion.findings.get("emotion_primary")
        
        emotion_to_angle = {
            "status": Angle.STATUS,
            "control": Angle.FUNCIONAL,
            "alivio": Angle.DOLOR,
            "seguridad": Angle.FUNCIONAL,
            "pertenencia": Angle.LIFESTYLE,
            "placer": Angle.LIFESTYLE,
        }
        
        if primary_emotion and primary_emotion in emotion_to_angle:
            return emotion_to_angle[primary_emotion]
        
        return Angle.DOLOR
    
    def _angles_to_avoid(self, emotion: FrameworkResult) -> List[Angle]:
        avoid = []
        
        primary = emotion.findings.get("emotion_primary")
        if primary == "control":
            avoid.append(Angle.REGALO)
        if primary == "status":
            avoid.append(Angle.AHORRO)
        
        return avoid
    
    def _generate_recommendations(
        self,
        ctx: ProductContext,
        results: Dict[str, FrameworkResult],
        verdict: InterrogationVerdict
    ) -> List[str]:
        recs = []
        
        if verdict == InterrogationVerdict.BLOCK:
            if results["compliance"].findings.get("is_critical"):
                recs.append("URGENTE: Eliminar claims médicos/salud del listing")
            if not results["objection_analysis"].findings.get("objection_response"):
                recs.append("Definir respuesta clara a objeción principal antes de lanzar")
        
        if verdict == InterrogationVerdict.NEEDS_WORK:
            if results["differentiation"].score < 0.5:
                recs.append("Crear bundle o ángulo único para diferenciarse")
            if results["emotion_map"].score < 0.5:
                recs.append("Clarificar qué emoción compra el cliente")
        
        if ctx.margin > 0.5:
            recs.append(f"Margen de {ctx.margin_pct:.0f}% permite invertir en garantía/soporte")
        
        return recs


# ============================================================
# HELPERS
# ============================================================

def quick_interrogate(
    product_id: str,
    name: str,
    category: str,
    price: float,
    cost: float,
    description: str = "",
) -> InterrogationResult:
    """Helper para interrogación rápida."""
    ctx = ProductContext(
        product_id=product_id,
        name=name,
        category=category,
        price=price,
        cost=cost,
        description=description,
    )
    
    engine = InterrogationEngine()
    return engine.interrogate(ctx)
