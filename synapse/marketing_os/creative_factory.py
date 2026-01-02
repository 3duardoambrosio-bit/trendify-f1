# synapse/marketing_os/creative_factory.py
"""
Creative Factory - Nivel F1

Genera contenido de marketing ejecutable:
- Hooks (10+)
- Scripts 7s/15s/30s
- Primary texts
- Headlines
- Landing skeletons
- Objection matrix

Diversidad real: ángulo × trigger × formato
Quality Filter aplicado a TODO.
"""

from __future__ import annotations

import hashlib
import itertools
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ProductContext,
    InterrogationResult,
    GeneratedContent,
    ContentType,
    Angle,
    Emotion,
    AdKitManifest,
)
from .quality_filter import QualityFilter


# ============================================================
# TEMPLATES
# ============================================================

HOOK_TEMPLATES = {
    Angle.DOLOR: [
        "¿Cansado de {enemy}? {product_name} lo soluciona en segundos",
        "Si {enemy} te tiene harto, esto es para ti",
        "Dile adiós a {enemy} con {product_name}",
        "{enemy}... el peor enemigo de tu día. Hasta ahora",
        "¿Cuántas veces {enemy} te ha arruinado el momento?",
    ],
    Angle.STATUS: [
        "Lo que usan los que saben de {category}",
        "No es para todos. Es para los que exigen más",
        "El secreto de los que siempre destacan",
        "Mientras otros usan genéricos, tú usas {product_name}",
        "Para los que no se conforman con lo básico",
    ],
    Angle.FUNCIONAL: [
        "{benefit_1} + {benefit_2} en un solo producto",
        "{number} horas de {main_feature}. Sin excusas",
        "Hace exactamente lo que promete: {main_feature}",
        "Simple: {benefit_1}. Punto",
        "{main_feature} que realmente funciona",
    ],
    Angle.AHORRO: [
        "Calidad de ${high_price} a precio de ${price}",
        "¿Por qué pagar más si {product_name} hace lo mismo?",
        "La alternativa inteligente que tu cartera agradece",
        "Mismo resultado, fracción del precio",
        "Lo que necesitas sin pagar de más",
    ],
    Angle.REGALO: [
        "El regalo que van a usar todos los días",
        "Para alguien especial que merece {benefit_1}",
        "Regala {benefit_1}, no otro objeto más",
        "El detalle perfecto para quien tiene todo",
        "Sorprende con algo que realmente van a usar",
    ],
}

SCRIPT_TEMPLATES = {
    "7s": {
        "hands_only": "🎬 [Manos mostrando producto]\n\"{hook}\"\n[Mostrar {main_feature}]\n\"Link en bio\"",
        "text_story": "🎬 [Texto en pantalla]\n\"{hook}\"\n[Corte rápido a producto]\n\"{benefit_1}\"",
        "comparison": "🎬 [Split screen]\nAntes: {enemy}\nDespués: {benefit_1}\n\"Link en bio\"",
    },
    "15s": {
        "hands_only": "🎬 [0-3s] Manos con problema: \"{enemy}\"\n[3-8s] Unboxing {product_name}\n[8-12s] Demo de {main_feature}\n[12-15s] \"¿Lo quieres? Link en bio\"",
        "voiceover": "🎬 [0-3s] B-roll producto\nVO: \"{hook}\"\n[3-10s] Demo {main_feature}\nVO: \"{benefit_1} + {benefit_2}\"\n[10-15s] CTA\nVO: \"Link en bio\"",
        "before_after": "🎬 [0-5s] ANTES: {enemy}\n[5-10s] DESPUÉS: {benefit_1}\n[10-15s] Producto + \"Tuyo por ${price}\"",
    },
    "30s": {
        "problem_solution": "🎬 [0-5s] Hook: \"{hook}\"\n[5-12s] El problema: {enemy} explicado\n[12-22s] La solución: {product_name}\n- {benefit_1}\n- {benefit_2}\n- {benefit_3}\n[22-28s] Prueba social o garantía\n[28-30s] CTA: \"Link en bio\"",
        "storytelling": "🎬 [0-8s] Historia relatable sobre {enemy}\n[8-15s] Descubrimiento de {product_name}\n[15-25s] Transformación:\n- Antes: {enemy}\n- Ahora: {benefit_1}\n[25-30s] \"¿Quieres lo mismo? Link en bio\"",
        "features_demo": "🎬 [0-5s] \"{hook}\"\n[5-10s] Feature 1: {benefit_1}\n[10-15s] Feature 2: {benefit_2}\n[15-20s] Feature 3: {benefit_3}\n[20-25s] Comparación con alternativas\n[25-30s] Precio + CTA",
    },
}

PRIMARY_TEXT_TEMPLATES = [
    "🔥 {hook}\n\n{benefit_1}. {benefit_2}. {benefit_3}.\n\nY lo mejor: {unique_feature}.\n\n👉 Compra ahora y {urgency}",
    "¿{enemy}? 🙄\n\nCon {product_name} eso se acabó.\n\n✅ {benefit_1}\n✅ {benefit_2}\n✅ {benefit_3}\n\n{cta}",
    "{hook}\n\nMira, {product_name} no es para todos.\n\nEs para los que quieren {benefit_1} sin {enemy}.\n\n{number}+ personas ya lo tienen. ¿Y tú?\n\n{cta}",
    "ESTO es lo que necesitas si:\n\n❌ {enemy}\n❌ Productos que no funcionan\n❌ Tirar tu dinero\n\n{product_name} = {benefit_1} garantizado.\n\n{cta}",
]

HEADLINE_TEMPLATES = [
    "{benefit_1} garantizado",
    "Adiós {enemy}",
    "{number} horas de {main_feature}",
    "Lo que todos quieren",
    "Por fin: {benefit_1}",
    "Tu nuevo favorito",
    "{main_feature} real",
    "Calidad premium, precio justo",
    "El original, no copias",
    "Envío express MX",
]

LANDING_SECTIONS = [
    "HERO: {hook} + imagen principal + CTA primario",
    "PROBLEMA: 3 pain points sobre {enemy}",
    "SOLUCIÓN: {product_name} como respuesta",
    "BENEFICIOS: {benefit_1}, {benefit_2}, {benefit_3}",
    "FEATURES: specs técnicas con iconos",
    "SOCIAL PROOF: reviews/testimonios",
    "GARANTÍA: política de devolución",
    "FAQ: top 5 preguntas",
    "CTA FINAL: urgency + botón comprar",
]


# ============================================================
# TRIGGERS & FORMATS
# ============================================================

TRIGGERS = ["frustration", "aspiration", "fear", "social_proof", "urgency", "curiosity"]

FORMATS = ["hands_only", "voiceover", "text_story", "comparison", "before_after", "unboxing"]

URGENCY_PHRASES = [
    "envío gratis hoy",
    "últimas unidades",
    "precio especial esta semana",
    "garantía de 30 días",
    "llega en 3-5 días",
]


# ============================================================
# CONTENT GENERATOR
# ============================================================

@dataclass
class CreativeFactory:
    """
    Fábrica de contenido de marketing.
    
    Uso:
        factory = CreativeFactory()
        kit = factory.generate_kit(product, interrogation_result)
    """
    
    quality_filter: QualityFilter = field(default_factory=QualityFilter)
    max_regenerations: int = 3
    
    def generate_kit(
        self,
        product: ProductContext,
        interrogation: Optional[InterrogationResult] = None,
        config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Genera kit completo de marketing.
        
        Returns:
            Dict con hooks, scripts, texts, headlines, landing, objections, manifest
        """
        config = config or {}
        
        # Build context for templates
        ctx = self._build_context(product, interrogation)
        
        # Generate each component
        hooks = self._generate_hooks(ctx, config.get("num_hooks", 10))
        scripts_7s = self._generate_scripts(ctx, "7s", config.get("num_scripts_7s", 5))
        scripts_15s = self._generate_scripts(ctx, "15s", config.get("num_scripts_15s", 5))
        scripts_30s = self._generate_scripts(ctx, "30s", config.get("num_scripts_30s", 5))
        primary_texts = self._generate_primary_texts(ctx, config.get("num_primary_texts", 10))
        headlines = self._generate_headlines(ctx, config.get("num_headlines", 10))
        landing = self._generate_landing_skeleton(ctx)
        objections = self._generate_objection_matrix(ctx, interrogation)
        
        # Build manifest
        manifest = self._build_manifest(
            product, interrogation, hooks, scripts_7s, scripts_15s, 
            scripts_30s, primary_texts, headlines
        )
        
        return {
            "hooks": hooks,
            "scripts_7s": scripts_7s,
            "scripts_15s": scripts_15s,
            "scripts_30s": scripts_30s,
            "primary_texts": primary_texts,
            "headlines": headlines,
            "landing_skeleton": landing,
            "objection_matrix": objections,
            "manifest": manifest,
        }
    
    def _build_context(
        self, 
        product: ProductContext, 
        interrogation: Optional[InterrogationResult]
    ) -> Dict[str, Any]:
        """Construye contexto para templates."""
        
        # Defaults
        enemy = "los problemas de siempre"
        benefits = ["calidad premium", "fácil de usar", "resultados reales"]
        main_feature = "rendimiento superior"
        
        if interrogation:
            enemy = interrogation.enemy or enemy
            main_feature = interrogation.job_to_be_done.replace("Contrátame para ", "") if interrogation.job_to_be_done else main_feature
        
        # Extract from product
        if product.unique_features:
            benefits = product.unique_features[:3]
            main_feature = product.unique_features[0]
        
        # Pad benefits if needed
        while len(benefits) < 3:
            benefits.append("envío rápido")
        
        return {
            "product_name": product.name[:30],  # Truncate
            "category": product.category.split("/")[-1] if "/" in product.category else product.category,
            "price": int(product.price),
            "high_price": int(product.price * 1.8),
            "enemy": enemy[:50],
            "benefit_1": benefits[0][:40],
            "benefit_2": benefits[1][:40],
            "benefit_3": benefits[2][:40],
            "main_feature": main_feature[:40],
            "unique_feature": benefits[0][:40],
            "number": random.choice(["20", "24", "30", "48", "100"]),
            "urgency": random.choice(URGENCY_PHRASES),
            "cta": "👉 Link en bio" if random.random() > 0.5 else "👉 Compra ahora",
        }
    
    def _fill_template(self, template: str, ctx: Dict[str, Any]) -> str:
        """Rellena template con contexto."""
        result = template
        for key, value in ctx.items():
            result = result.replace("{" + key + "}", str(value))
        return result
    
    def _generate_hooks(self, ctx: Dict, num: int) -> List[Dict]:
        """Genera hooks diversos."""
        hooks = []
        seen_content = set()
        
        # Get angles to use
        angles = list(HOOK_TEMPLATES.keys())
        
        # Generate combinations
        for angle in itertools.cycle(angles):
            if len(hooks) >= num:
                break
            
            templates = HOOK_TEMPLATES.get(angle, HOOK_TEMPLATES[Angle.DOLOR])
            template = random.choice(templates)
            
            # Fill and add hook context
            hook_ctx = {**ctx, "hook": ""}
            content = self._fill_template(template, hook_ctx)
            
            # Skip if too similar
            content_hash = hashlib.md5(content.lower().encode()).hexdigest()[:8]
            if content_hash in seen_content:
                continue
            seen_content.add(content_hash)
            
            # Quality check
            result = self.quality_filter.check(content, ContentType.HOOK)
            
            if result.passed:
                hooks.append({
                    "content": content,
                    "angle": angle.value,
                    "quality_score": result.total_score,
                    "variant_id": f"H{len(hooks)+1}_{angle.value[:3]}",
                })
        
        self.quality_filter.reset()
        return hooks[:num]
    
    def _generate_scripts(self, ctx: Dict, length: str, num: int) -> List[Dict]:
        """Genera scripts de duración específica."""
        scripts = []
        templates = SCRIPT_TEMPLATES.get(length, SCRIPT_TEMPLATES["15s"])
        
        # Generate a hook for context
        hook_template = random.choice(HOOK_TEMPLATES[Angle.DOLOR])
        hook = self._fill_template(hook_template, ctx)
        script_ctx = {**ctx, "hook": hook}
        
        formats_cycle = itertools.cycle(templates.keys())
        
        for fmt in formats_cycle:
            if len(scripts) >= num:
                break
            
            template = templates[fmt]
            content = self._fill_template(template, script_ctx)
            
            # Map length to content type
            content_type = {
                "7s": ContentType.SCRIPT_7S,
                "15s": ContentType.SCRIPT_15S,
                "30s": ContentType.SCRIPT_30S,
            }.get(length, ContentType.SCRIPT_15S)
            
            result = self.quality_filter.check(content, content_type)
            
            scripts.append({
                "content": content,
                "format": fmt,
                "duration": length,
                "quality_score": result.total_score,
                "variant_id": f"S{length}_{len(scripts)+1}_{fmt[:4]}",
            })
        
        self.quality_filter.reset()
        return scripts[:num]
    
    def _generate_primary_texts(self, ctx: Dict, num: int) -> List[Dict]:
        """Genera primary texts para ads."""
        texts = []
        
        # Generate hook for each
        for i, template in enumerate(itertools.cycle(PRIMARY_TEXT_TEMPLATES)):
            if len(texts) >= num:
                break
            
            hook_template = random.choice(HOOK_TEMPLATES[Angle.DOLOR])
            hook = self._fill_template(hook_template, ctx)
            text_ctx = {**ctx, "hook": hook}
            
            content = self._fill_template(template, text_ctx)
            result = self.quality_filter.check(content, ContentType.PRIMARY_TEXT)
            
            texts.append({
                "content": content,
                "quality_score": result.total_score,
                "variant_id": f"PT{len(texts)+1}",
            })
        
        self.quality_filter.reset()
        return texts[:num]
    
    def _generate_headlines(self, ctx: Dict, num: int) -> List[Dict]:
        """Genera headlines."""
        headlines = []
        seen = set()
        
        for template in itertools.cycle(HEADLINE_TEMPLATES):
            if len(headlines) >= num:
                break
            
            content = self._fill_template(template, ctx)
            
            if content.lower() in seen:
                continue
            seen.add(content.lower())
            
            result = self.quality_filter.check(content, ContentType.HEADLINE)
            
            headlines.append({
                "content": content,
                "quality_score": result.total_score,
                "variant_id": f"HL{len(headlines)+1}",
            })
        
        self.quality_filter.reset()
        return headlines[:num]
    
    def _generate_landing_skeleton(self, ctx: Dict) -> Dict:
        """Genera estructura de landing page."""
        sections = []
        
        for section in LANDING_SECTIONS:
            filled = self._fill_template(section, ctx)
            sections.append(filled)
        
        return {
            "sections": sections,
            "total_sections": len(sections),
            "estimated_length": "1200-1500 palabras",
        }
    
    def _generate_objection_matrix(
        self, 
        ctx: Dict, 
        interrogation: Optional[InterrogationResult]
    ) -> Dict:
        """Genera matriz de objeciones y respuestas."""
        
        objections = [
            {
                "objection": "¿Es de buena calidad?",
                "response": f"Garantía de 30 días. Si no te convence, te devolvemos tu dinero.",
                "evidence": "Política de devolución clara",
            },
            {
                "objection": "¿Cuánto tarda en llegar?",
                "response": "Envío express 3-5 días a todo México.",
                "evidence": "Rastreo incluido",
            },
            {
                "objection": "¿Por qué es tan barato?",
                "response": "Vendemos directo, sin intermediarios. Misma calidad, mejor precio.",
                "evidence": "Comparación con retail",
            },
        ]
        
        # Add from interrogation if available
        if interrogation and interrogation.killing_objection:
            objections.insert(0, {
                "objection": interrogation.killing_objection,
                "response": interrogation.objection_response or "Garantizado",
                "evidence": "Respuesta específica del producto",
            })
        
        return {
            "objections": objections,
            "total": len(objections),
        }
    
    def _build_manifest(
        self,
        product: ProductContext,
        interrogation: Optional[InterrogationResult],
        hooks: List, scripts_7s: List, scripts_15s: List,
        scripts_30s: List, primary_texts: List, headlines: List,
    ) -> AdKitManifest:
        """Construye manifest del kit."""
        
        # Calculate average quality
        all_scores = (
            [h["quality_score"] for h in hooks] +
            [s["quality_score"] for s in scripts_7s] +
            [s["quality_score"] for s in scripts_15s] +
            [s["quality_score"] for s in scripts_30s] +
            [t["quality_score"] for t in primary_texts] +
            [h["quality_score"] for h in headlines]
        )
        avg_quality = sum(all_scores) / len(all_scores) if all_scores else 0
        
        manifest = AdKitManifest(
            product_id=product.product_id,
            product_name=product.name,
            hooks_count=len(hooks),
            scripts_7s_count=len(scripts_7s),
            scripts_15s_count=len(scripts_15s),
            scripts_30s_count=len(scripts_30s),
            primary_texts_count=len(primary_texts),
            headlines_count=len(headlines),
            landing_skeletons_count=1,
            quality_score=avg_quality,
            input_hash=product.input_hash(),
        )
        
        if interrogation:
            manifest.interrogation_verdict = interrogation.verdict.value
            manifest.interrogation_score = interrogation.total_score
            manifest.angles_used = [interrogation.recommended_angle.value]
        
        return manifest


# ============================================================
# HELPER FUNCTION
# ============================================================

def quick_generate(
    product_id: str,
    name: str,
    category: str,
    price: float,
    cost: float,
) -> Dict[str, Any]:
    """Helper para generación rápida."""
    from .interrogation_engine import InterrogationEngine
    
    product = ProductContext(
        product_id=product_id,
        name=name,
        category=category,
        price=price,
        cost=cost,
    )
    
    engine = InterrogationEngine()
    interrogation = engine.interrogate(product)
    
    factory = CreativeFactory()
    return factory.generate_kit(product, interrogation)
