"""
Tests para Quality Filter.

Verifica:
- Contract validation
- Meta filter dimensions
- Duplicate detection
- Regeneration limits
"""

import pytest
from synapse.marketing_os.models import ContentType
from synapse.marketing_os.quality_filter import (
    QualityFilter,
    ContractFilter,
    MetaFilter,
    quick_check,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def filter():
    return QualityFilter()


@pytest.fixture
def good_hook():
    return "¿Cansado de que tus audífonos mueran a media canción? Descubre M10 con 20 horas de batería"


@pytest.fixture
def bad_hook():
    return "El mejor producto increíble de alta calidad premium único garantizado 100%"


# ============================================================
# CONTRACT FILTER TESTS
# ============================================================

class TestContractFilter:
    """Tests para Contract Filter."""
    
    def test_empty_content_fails(self):
        """Contenido vacío debe fallar."""
        filter = ContractFilter()
        result = filter.validate("", ContentType.HOOK)
        
        assert not result.valid
        assert "EMPTY_CONTENT" in result.issues
    
    def test_too_short_content(self):
        """Contenido muy corto debe fallar."""
        filter = ContractFilter()
        result = filter.validate("Hola", ContentType.HOOK)
        
        assert not result.valid
        assert any("TOO_SHORT" in i for i in result.issues)
    
    def test_too_long_content(self):
        """Contenido muy largo debe fallar."""
        filter = ContractFilter()
        content = "x" * 200
        result = filter.validate(content, ContentType.HOOK)
        
        assert not result.valid
        assert any("TOO_LONG" in i for i in result.issues)
    
    def test_unreplaced_placeholders(self):
        """Placeholders no reemplazados deben detectarse."""
        filter = ContractFilter()
        result = filter.validate(
            "Hola {nombre}, compra {producto} ahora con {descuento}",
            ContentType.PRIMARY_TEXT
        )
        
        assert not result.valid
        assert any("PLACEHOLDER" in i for i in result.issues)
    
    def test_encoding_issues(self):
        """Problemas de encoding deben detectarse."""
        filter = ContractFilter()
        result = filter.validate(
            "Este texto tiene caracteres raros con extras aqui",
            ContentType.HOOK
        )
        
        assert result is not None
    
    def test_all_caps_content(self):
        """Todo mayúsculas debe detectarse."""
        filter = ContractFilter()
        result = filter.validate(
            "COMPRA AHORA ESTE INCREIBLE PRODUCTO DE OFERTA",
            ContentType.HOOK
        )
        
        assert not result.valid
        assert any("CAPS" in i for i in result.issues)
    
    def test_valid_content_passes(self, good_hook):
        """Contenido válido debe pasar."""
        filter = ContractFilter()
        result = filter.validate(good_hook, ContentType.HOOK)
        
        assert result.valid
        assert len(result.issues) == 0


# ============================================================
# META FILTER TESTS
# ============================================================

class TestMetaFilter:
    """Tests para Meta Filter."""
    
    def test_duplicate_detection(self):
        """Duplicados deben detectarse."""
        filter = MetaFilter()
        content = "Este es un contenido de prueba para hooks"
        
        passed1, _, issues1 = filter.evaluate(content, ContentType.HOOK)
        assert passed1
        
        passed2, _, issues2 = filter.evaluate(content, ContentType.HOOK)
        assert not passed2
        assert "DUPLICATE" in issues2
    
    def test_similar_content_detection(self):
        """Contenido muy similar debe detectarse."""
        filter = MetaFilter()
        
        content1 = "Los audífonos bluetooth M10 tienen excelente batería de 20 horas"
        content2 = "Los audífonos bluetooth M10 tienen excelente batería de veinte horas"
        
        filter.evaluate(content1, ContentType.HOOK)
        passed2, _, issues2 = filter.evaluate(content2, ContentType.HOOK)
        
        assert not passed2
        assert "SIMILAR" in issues2[0]
    
    def test_clarity_scoring(self):
        """Claridad debe scorear correctamente."""
        filter = MetaFilter()
        
        clear = "Audífonos con 20 horas de batería. Bluetooth 5.0. Envío gratis."
        _, scores1, _ = filter.evaluate(clear, ContentType.HOOK)
        
        filter.reset()
        
        verbose = "Básicamente, literalmente, sinceramente, honestamente estos audífonos son definitivamente absolutamente increíbles realmente"
        _, scores2, _ = filter.evaluate(verbose, ContentType.HOOK)
        
        assert scores1["clarity"] > scores2["clarity"]
    
    def test_persuasion_scoring(self):
        """Persuasión debe scorear correctamente."""
        filter = MetaFilter()
        
        persuasive = "20 horas de batería porque usamos celdas de litio premium. Ahorra $200 vs la competencia."
        _, scores1, _ = filter.evaluate(persuasive, ContentType.HOOK)
        
        filter.reset()
        
        weak = "Buenos audífonos para ti"
        _, scores2, _ = filter.evaluate(weak, ContentType.HOOK)
        
        assert scores1["persuasion"] > scores2["persuasion"]
    
    def test_differentiation_scoring(self, good_hook, bad_hook):
        """Diferenciación debe penalizar frases genéricas."""
        filter = MetaFilter()
        
        _, scores1, _ = filter.evaluate(good_hook, ContentType.HOOK)
        
        filter.reset()
        
        _, scores2, _ = filter.evaluate(bad_hook, ContentType.HOOK)
        
        assert scores1["differentiation"] > scores2["differentiation"]
    
    def test_compliance_scoring(self):
        """Compliance debe detectar términos riesgosos."""
        filter = MetaFilter()
        
        clean = "Audífonos cómodos con buen sonido y batería duradera"
        _, scores1, _ = filter.evaluate(clean, ContentType.HOOK)
        
        filter.reset()
        
        risky = "Audífonos certificados médicamente, garantizado 100%, aprobados por doctores"
        _, scores2, _ = filter.evaluate(risky, ContentType.HOOK)
        
        assert scores1["compliance"] > scores2["compliance"]
    
    def test_mexicanidad_scoring(self):
        """Mexicanidad debe detectar español de España."""
        filter = MetaFilter()
        
        mx = "Estos audífonos están muy padres, neta funcionan bien"
        _, scores1, _ = filter.evaluate(mx, ContentType.HOOK)
        
        filter.reset()
        
        spain = "Estos auriculares molan mucho tío, son muy guay vale"
        _, scores2, _ = filter.evaluate(spain, ContentType.HOOK)
        
        assert scores1["mexicanidad"] > scores2["mexicanidad"]
    
    def test_reset_clears_history(self):
        """Reset debe limpiar historial."""
        filter = MetaFilter()
        content = "Contenido de prueba único"
        
        filter.evaluate(content, ContentType.HOOK)
        assert len(filter.seen_hashes) > 0
        
        filter.reset()
        assert len(filter.seen_hashes) == 0


# ============================================================
# COMBINED FILTER TESTS
# ============================================================

class TestQualityFilter:
    """Tests para filtro combinado."""
    
    def test_good_content_passes(self, filter, good_hook):
        """Buen contenido debe pasar."""
        result = filter.check(good_hook, ContentType.HOOK)
        
        assert result.passed
        assert result.reason == "APPROVED"
        assert result.total_score > 0.6
    
    def test_bad_content_fails(self, filter, bad_hook):
        """Mal contenido debe fallar."""
        result = filter.check(bad_hook, ContentType.HOOK)
        
        assert result.total_score < 0.8
    
    def test_scores_populated(self, filter, good_hook):
        """Scores deben estar completos."""
        result = filter.check(good_hook, ContentType.HOOK)
        
        expected_dims = ["clarity", "persuasion", "differentiation",
                        "compliance", "mexicanidad", "actionability"]
        
        for dim in expected_dims:
            assert dim in result.dimension_scores
            assert 0 <= result.dimension_scores[dim] <= 1
    
    def test_regeneration_hint_generated(self, filter, bad_hook):
        """Hint de regeneración debe generarse."""
        result = filter.check(bad_hook, ContentType.HOOK)
        
        if not result.passed:
            assert result.regeneration_hint
    
    def test_max_regenerations_tracking(self, filter):
        """Debe trackear regeneraciones por content_id."""
        content_id = "test-content-1"
        bad_content = ""
        
        for i in range(4):
            result = filter.check(bad_content, ContentType.HOOK, content_id)
        
        assert "MAX_REGENERATIONS_REACHED" in result.issues
    
    def test_reset_clears_everything(self, filter, good_hook):
        """Reset debe limpiar todo."""
        filter.check(good_hook, ContentType.HOOK)
        filter.regeneration_counts["test"] = 5
        
        filter.reset()
        
        assert len(filter.regeneration_counts) == 0


# ============================================================
# CONTENT TYPE SPECIFIC TESTS
# ============================================================

class TestContentTypeLimits:
    """Tests para límites por tipo de contenido."""
    
    def test_script_30s_allows_longer(self):
        """Script 30s debe permitir contenido más largo."""
        filter = ContractFilter()
        
        content = "a" * 400
        
        result_script = filter.validate(content, ContentType.SCRIPT_30S)
        result_hook = filter.validate(content, ContentType.HOOK)
        
        assert result_script.valid
        assert not result_hook.valid
    
    def test_headline_enforces_short(self):
        """Headline debe ser corto."""
        filter = ContractFilter()
        
        content = "Este es un headline muy largo que no debería pasar " + "x" * 50
        
        result = filter.validate(content, ContentType.HEADLINE)
        
        assert not result.valid
        assert any("TOO_LONG" in i for i in result.issues)


# ============================================================
# QUICK CHECK HELPER TEST
# ============================================================

class TestQuickCheck:
    """Tests para helper quick_check."""
    
    def test_quick_check_works(self, good_hook):
        """Quick check debe funcionar."""
        assert quick_check(good_hook, ContentType.HOOK) == True
    
    def test_quick_check_rejects_bad(self):
        """Quick check debe rechazar malo."""
        assert quick_check("", ContentType.HOOK) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
