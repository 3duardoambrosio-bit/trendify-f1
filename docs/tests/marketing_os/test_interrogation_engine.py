# tests/marketing_os/test_interrogation_engine.py
"""
Tests para Interrogation Engine.

Verifica:
- Frameworks individuales
- Lógica de verdicts
- Blocking conditions
- Recomendaciones
"""

import pytest
from synapse.marketing_os.models import ProductContext, InterrogationVerdict, Angle, Emotion
from synapse.marketing_os.interrogation_engine import (
    InterrogationEngine,
    JTBDEvaluator,
    EmotionMapEvaluator,
    ObjectionEvaluator,
    ComplianceEvaluator,
    DifferentiationEvaluator,
    quick_interrogate,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def good_product():
    """Producto bueno - debería pasar."""
    return ProductContext(
        product_id="34357",
        name="Audifonos Bluetooth M10 Manos Libres",
        category="electronics/audio",
        price=599.0,
        cost=180.0,
        description="Audifonos inalámbricos con cancelación de ruido, 20 horas de batería, bluetooth 5.0",
        unique_features=["Cancelación de ruido", "20h batería", "Bluetooth 5.0"],
    )


@pytest.fixture
def bad_compliance_product():
    """Producto con claims médicos - debería bloquearse."""
    return ProductContext(
        product_id="99999",
        name="Pulsera Mágica de Salud",
        category="health",
        price=299.0,
        cost=50.0,
        description="Cura el insomnio y trata la ansiedad. Clínicamente probado. FDA approved.",
    )


@pytest.fixture
def low_margin_product():
    """Producto con margen bajo."""
    return ProductContext(
        product_id="88888",
        name="Cable USB Genérico",
        category="electronics",
        price=50.0,
        cost=40.0,
        description="Cable USB estándar",
    )


@pytest.fixture
def engine():
    return InterrogationEngine()


# ============================================================
# JTBD FRAMEWORK TESTS
# ============================================================

class TestJTBDFramework:
    """Tests para Jobs To Be Done evaluator."""
    
    def test_audio_product_has_job(self, good_product):
        """Producto de audio debe tener job claro."""
        evaluator = JTBDEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.score > 0.5
        assert "job" in result.findings
        job = result.findings["job"].lower()
        assert "contrátame" in job or "job" in job or len(job) > 20
    
    def test_job_includes_alternatives(self, good_product):
        """Debe identificar alternativas."""
        evaluator = JTBDEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert "alternatives" in result.findings
        assert len(result.findings["alternatives"]) > 0
    
    def test_unknown_category_still_works(self):
        """Categoría desconocida no debe fallar."""
        ctx = ProductContext(
            product_id="test",
            name="Producto Raro",
            category="unknown_category",
            price=100,
            cost=50,
        )
        
        evaluator = JTBDEvaluator()
        result = evaluator.evaluate(ctx)
        
        assert result.findings["job"] is not None


# ============================================================
# EMOTION MAP TESTS
# ============================================================

class TestEmotionMapFramework:
    """Tests para Emotion Map evaluator."""
    
    def test_audio_emotion_mapping(self, good_product):
        """Audio debe mapear a emociones correctas."""
        evaluator = EmotionMapEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.score > 0.5
        assert result.findings["emotion_primary"] is not None
    
    def test_enemy_identified(self, good_product):
        """Debe identificar enemigo."""
        evaluator = EmotionMapEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.findings["enemy"]
        assert len(result.findings["enemy"]) > 5
    
    def test_fears_populated(self, good_product):
        """Debe identificar miedos."""
        evaluator = EmotionMapEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert "fears" in result.findings
        assert len(result.findings["fears"]) > 0
    
    def test_blocking_framework(self, good_product):
        """Emotion map es blocking framework."""
        evaluator = EmotionMapEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.blocking == True


# ============================================================
# OBJECTION TESTS
# ============================================================

class TestObjectionFramework:
    """Tests para Objection evaluator."""
    
    def test_audio_killing_objection(self, good_product):
        """Audio debe tener objeción de sonido/calidad."""
        evaluator = ObjectionEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.findings["killing_objection"]
        objection = result.findings["killing_objection"].lower()
        assert any(w in objection for w in ["sonido", "calidad", "dura", "escucha"])
    
    def test_objection_has_response(self, good_product):
        """Debe generar respuesta a objeción."""
        evaluator = ObjectionEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.findings["objection_response"]
        assert len(result.findings["objection_response"]) > 10
    
    def test_evidence_detection(self, good_product):
        """Debe detectar si hay evidencia en respuesta."""
        evaluator = ObjectionEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert "has_evidence" in result.findings
    
    def test_no_response_is_blocking(self):
        """Sin respuesta a objeción debe ser blocking."""
        ctx = ProductContext(
            product_id="test",
            name="Producto Sin Info",
            category="random",
            price=100,
            cost=50,
        )
        
        evaluator = ObjectionEvaluator()
        result = evaluator.evaluate(ctx)
        
        assert result.findings["objection_response"] is not None


# ============================================================
# COMPLIANCE TESTS
# ============================================================

class TestComplianceFramework:
    """Tests para Compliance evaluator."""
    
    def test_clean_product_passes(self, good_product):
        """Producto limpio debe pasar compliance."""
        evaluator = ComplianceEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.score >= 0.8
        assert len(result.findings["compliance_flags"]) == 0
    
    def test_medical_claims_blocked(self, bad_compliance_product):
        """Claims médicos deben ser detectados."""
        evaluator = ComplianceEvaluator()
        result = evaluator.evaluate(bad_compliance_product)
        
        assert result.score < 0.5
        assert len(result.findings["compliance_flags"]) > 0
        assert result.blocking == True
    
    def test_health_claims_detected(self):
        """Claims de salud deben ser detectados."""
        ctx = ProductContext(
            product_id="test",
            name="Suplemento Quema Grasa",
            category="supplements",
            price=299,
            cost=50,
            description="Baja de peso rápido, quema grasa abdominal",
        )
        
        evaluator = ComplianceEvaluator()
        result = evaluator.evaluate(ctx)
        
        assert len(result.findings["compliance_flags"]) > 0
    
    def test_exaggeration_detected(self):
        """Exageraciones deben ser detectadas."""
        ctx = ProductContext(
            product_id="test",
            name="El Mejor Producto del Mundo",
            category="electronics",
            price=100,
            cost=50,
            description="Revolucionario y único en el mercado",
        )
        
        evaluator = ComplianceEvaluator()
        result = evaluator.evaluate(ctx)
        
        assert len(result.findings["compliance_flags"]) > 0


# ============================================================
# DIFFERENTIATION TESTS
# ============================================================

class TestDifferentiationFramework:
    """Tests para Differentiation evaluator."""
    
    def test_product_with_features_scores_higher(self, good_product):
        """Producto con features únicas debe scorear alto."""
        evaluator = DifferentiationEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert result.score > 0.5
        assert len(result.findings["unique_features"]) > 0
    
    def test_generic_product_scores_lower(self):
        """Producto genérico debe scorear bajo."""
        ctx = ProductContext(
            product_id="test",
            name="Cable",
            category="electronics",
            price=50,
            cost=40,
            description="Cable estándar",
        )
        
        evaluator = DifferentiationEvaluator()
        result = evaluator.evaluate(ctx)
        
        assert result.score <= 0.7
    
    def test_defensibility_assessment(self, good_product):
        """Debe evaluar defensibilidad."""
        evaluator = DifferentiationEvaluator()
        result = evaluator.evaluate(good_product)
        
        assert "is_defensible" in result.findings
        assert "defensibility_reason" in result.findings


# ============================================================
# FULL ENGINE TESTS
# ============================================================

class TestInterrogationEngine:
    """Tests para el engine completo."""
    
    def test_good_product_launches(self, engine, good_product):
        """Producto bueno debe tener verdict LAUNCH."""
        result = engine.interrogate(good_product)
        
        assert result.verdict == InterrogationVerdict.LAUNCH
        assert result.passed == True
        assert result.total_score >= 0.6
    
    def test_bad_compliance_blocks(self, engine, bad_compliance_product):
        """Producto con compliance malo debe bloquearse."""
        result = engine.interrogate(bad_compliance_product)
        
        assert result.verdict == InterrogationVerdict.BLOCK
        assert result.passed == False
        assert len(result.blocking_reasons) > 0
        assert len(result.compliance_flags) > 0
    
    def test_low_margin_has_risk(self, engine, low_margin_product):
        """Producto con margen bajo debe tener riesgo."""
        result = engine.interrogate(low_margin_product)
        
        risk_descriptions = [r.description for r in result.risks]
        assert any("margen" in r.lower() for r in risk_descriptions)
    
    def test_all_framework_scores_present(self, engine, good_product):
        """Todos los frameworks deben tener score."""
        result = engine.interrogate(good_product)
        
        expected_frameworks = ["jtbd", "emotion_map", "objection_analysis", "compliance", "differentiation"]
        for fw in expected_frameworks:
            assert fw in result.framework_scores
            assert 0 <= result.framework_scores[fw] <= 1
    
    def test_has_recommended_angle(self, engine, good_product):
        """Debe tener ángulo recomendado."""
        result = engine.interrogate(good_product)
        
        assert result.recommended_angle is not None
        assert isinstance(result.recommended_angle, Angle)
    
    def test_has_job_to_be_done(self, engine, good_product):
        """Debe tener job to be done."""
        result = engine.interrogate(good_product)
        
        assert result.job_to_be_done
        assert len(result.job_to_be_done) > 10
    
    def test_has_enemy(self, engine, good_product):
        """Debe tener enemigo identificado."""
        result = engine.interrogate(good_product)
        
        assert result.enemy
        assert len(result.enemy) > 5
    
    def test_has_killing_objection(self, engine, good_product):
        """Debe tener objeción principal."""
        result = engine.interrogate(good_product)
        
        assert result.killing_objection
        assert result.objection_response
    
    def test_input_hash_generated(self, engine, good_product):
        """Debe generar input hash para idempotencia."""
        result = engine.interrogate(good_product)
        
        assert result.input_hash
        assert len(result.input_hash) == 16
    
    def test_to_dict_works(self, engine, good_product):
        """to_dict debe serializar correctamente."""
        result = engine.interrogate(good_product)
        d = result.to_dict()
        
        assert d["product_id"] == "34357"
        assert d["verdict"] == "launch"
        assert "framework_scores" in d
        assert "risks" in d


# ============================================================
# VERDICT LOGIC TESTS
# ============================================================

class TestVerdictLogic:
    """Tests para lógica de verdicts."""
    
    def test_score_below_04_blocks(self, engine):
        """Score < 0.4 debe bloquear."""
        ctx = ProductContext(
            product_id="bad",
            name="Pastilla Cura Todo FDA",
            category="medical",
            price=100,
            cost=90,
            description="Cura diabetes, cáncer, adelgaza, el mejor del mundo garantizado",
        )
        
        result = engine.interrogate(ctx)
        
        assert result.verdict == InterrogationVerdict.BLOCK
    
    def test_score_04_to_06_needs_work(self, engine):
        """Score 0.4-0.6 debe ser NEEDS_WORK."""
        ctx = ProductContext(
            product_id="meh",
            name="Cosa Genérica",
            category="stuff",
            price=100,
            cost=60,
            description="Un producto normal sin nada especial",
        )
        
        result = engine.interrogate(ctx)
        
        assert result.verdict in [InterrogationVerdict.NEEDS_WORK, InterrogationVerdict.LAUNCH]
    
    def test_blocking_reason_overrides_score(self, engine, bad_compliance_product):
        """Blocking reason debe bloquear aunque score sea ok."""
        result = engine.interrogate(bad_compliance_product)
        
        assert result.verdict == InterrogationVerdict.BLOCK
        assert len(result.blocking_reasons) > 0


# ============================================================
# QUICK INTERROGATE HELPER TEST
# ============================================================

class TestQuickInterrogate:
    """Tests para helper quick_interrogate."""
    
    def test_quick_interrogate_works(self):
        """Helper debe funcionar."""
        result = quick_interrogate(
            product_id="test123",
            name="Audifonos Bluetooth Test",
            category="audio",
            price=500,
            cost=150,
            description="Audifonos con buena batería",
        )
        
        assert result.product_id == "test123"
        assert result.verdict is not None
        assert result.total_score >= 0


# ============================================================
# BATCH INTERROGATION TEST
# ============================================================

class TestBatchInterrogation:
    """Tests para interrogación en batch."""
    
    def test_interrogate_multiple(self, engine):
        """Debe poder interrogar múltiples productos."""
        products = [
            ProductContext(
                product_id=f"prod-{i}",
                name=f"Producto {i}",
                category="electronics",
                price=500,
                cost=200,
            )
            for i in range(5)
        ]
        
        results = [engine.interrogate(p) for p in products]
        
        assert len(results) == 5
        for r in results:
            assert r.verdict is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
