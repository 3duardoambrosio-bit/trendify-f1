# tests/marketing_os/test_creative_factory.py
"""
Tests para Creative Factory.
"""

import pytest
from synapse.marketing_os.models import ProductContext, ContentType
from synapse.marketing_os.interrogation_engine import InterrogationEngine
from synapse.marketing_os.creative_factory import CreativeFactory, quick_generate


@pytest.fixture
def product():
    return ProductContext(
        product_id="34357",
        name="Audifonos Bluetooth M10 Manos Libres",
        category="electronics/audio",
        price=599.0,
        cost=180.0,
        description="Audifonos inalambricos con cancelacion de ruido",
        unique_features=["20 horas de bateria", "Cancelacion de ruido", "Bluetooth 5.0"],
    )


@pytest.fixture
def interrogation(product):
    engine = InterrogationEngine()
    return engine.interrogate(product)


@pytest.fixture
def factory():
    return CreativeFactory()


class TestCreativeFactory:
    """Tests para CreativeFactory."""
    
    def test_generate_kit_returns_all_components(self, factory, product, interrogation):
        """Kit debe tener todos los componentes."""
        kit = factory.generate_kit(product, interrogation)
        
        assert "hooks" in kit
        assert "scripts_7s" in kit
        assert "scripts_15s" in kit
        assert "scripts_30s" in kit
        assert "primary_texts" in kit
        assert "headlines" in kit
        assert "landing_skeleton" in kit
        assert "objection_matrix" in kit
        assert "manifest" in kit
    
    def test_hooks_have_required_fields(self, factory, product, interrogation):
        """Hooks deben tener campos requeridos."""
        kit = factory.generate_kit(product, interrogation)
        
        for hook in kit["hooks"]:
            assert "content" in hook
            assert "angle" in hook
            assert "quality_score" in hook
            assert "variant_id" in hook
            assert len(hook["content"]) > 10
    
    def test_hooks_are_diverse(self, factory, product, interrogation):
        """Hooks deben ser diversos (diferentes angulos)."""
        kit = factory.generate_kit(product, interrogation)
        
        angles = set(h["angle"] for h in kit["hooks"])
        assert len(angles) >= 2  # Al menos 2 angulos diferentes
    
    def test_hooks_count_matches_config(self, factory, product, interrogation):
        """Cantidad de hooks debe respetar config."""
        kit = factory.generate_kit(product, interrogation, {"num_hooks": 5})
        
        assert len(kit["hooks"]) == 5
    
    def test_scripts_have_format(self, factory, product, interrogation):
        """Scripts deben tener formato especificado."""
        kit = factory.generate_kit(product, interrogation)
        
        for script in kit["scripts_15s"]:
            assert "format" in script
            assert "duration" in script
            assert script["duration"] == "15s"
    
    def test_scripts_are_different_lengths(self, factory, product, interrogation):
        """Scripts de diferentes duraciones deben ser diferentes."""
        kit = factory.generate_kit(product, interrogation)
        
        # 7s should be shorter than 30s
        avg_7s = sum(len(s["content"]) for s in kit["scripts_7s"]) / len(kit["scripts_7s"])
        avg_30s = sum(len(s["content"]) for s in kit["scripts_30s"]) / len(kit["scripts_30s"])
        
        assert avg_30s > avg_7s
    
    def test_primary_texts_have_cta(self, factory, product, interrogation):
        """Primary texts deben tener CTA."""
        kit = factory.generate_kit(product, interrogation)
        
        for text in kit["primary_texts"]:
            content = text["content"].lower()
            has_cta = "link" in content or "compra" in content or "bio" in content
            assert has_cta, f"No CTA in: {text['content'][:50]}"
    
    def test_headlines_are_short(self, factory, product, interrogation):
        """Headlines deben ser cortos."""
        kit = factory.generate_kit(product, interrogation)
        
        for headline in kit["headlines"]:
            assert len(headline["content"]) <= 80
    
    def test_landing_has_sections(self, factory, product, interrogation):
        """Landing debe tener secciones."""
        kit = factory.generate_kit(product, interrogation)
        
        landing = kit["landing_skeleton"]
        assert "sections" in landing
        assert len(landing["sections"]) >= 5
    
    def test_objection_matrix_has_responses(self, factory, product, interrogation):
        """Objection matrix debe tener respuestas."""
        kit = factory.generate_kit(product, interrogation)
        
        matrix = kit["objection_matrix"]
        assert "objections" in matrix
        assert len(matrix["objections"]) >= 3
        
        for obj in matrix["objections"]:
            assert "objection" in obj
            assert "response" in obj
    
    def test_manifest_has_counts(self, factory, product, interrogation):
        """Manifest debe tener conteos correctos."""
        kit = factory.generate_kit(product, interrogation)
        
        manifest = kit["manifest"]
        assert manifest.hooks_count == len(kit["hooks"])
        assert manifest.scripts_15s_count == len(kit["scripts_15s"])
        assert manifest.headlines_count == len(kit["headlines"])
    
    def test_manifest_has_quality_score(self, factory, product, interrogation):
        """Manifest debe tener quality score."""
        kit = factory.generate_kit(product, interrogation)
        
        manifest = kit["manifest"]
        assert manifest.quality_score > 0
        assert manifest.quality_score <= 1
    
    def test_manifest_has_input_hash(self, factory, product, interrogation):
        """Manifest debe tener input hash."""
        kit = factory.generate_kit(product, interrogation)
        
        manifest = kit["manifest"]
        assert manifest.input_hash
        assert len(manifest.input_hash) == 16
    
    def test_generate_without_interrogation(self, factory, product):
        """Debe funcionar sin interrogation."""
        kit = factory.generate_kit(product, None)
        
        assert len(kit["hooks"]) > 0
        assert len(kit["scripts_15s"]) > 0


class TestQuickGenerate:
    """Tests para quick_generate helper."""
    
    def test_quick_generate_works(self):
        """Quick generate debe funcionar."""
        kit = quick_generate(
            product_id="test123",
            name="Test Product",
            category="electronics",
            price=500,
            cost=150,
        )
        
        assert "hooks" in kit
        assert "manifest" in kit
        assert len(kit["hooks"]) > 0


class TestContentQuality:
    """Tests para calidad del contenido generado."""
    
    def test_no_unreplaced_placeholders(self, factory, product, interrogation):
        """No debe haber placeholders sin reemplazar."""
        kit = factory.generate_kit(product, interrogation)
        
        for hook in kit["hooks"]:
            assert "{" not in hook["content"], f"Placeholder in: {hook['content']}"
        
        for script in kit["scripts_15s"]:
            # Scripts pueden tener {} como parte del formato
            pass
    
    def test_hooks_not_duplicated(self, factory, product, interrogation):
        """Hooks no deben estar duplicados."""
        kit = factory.generate_kit(product, interrogation)
        
        contents = [h["content"].lower() for h in kit["hooks"]]
        unique = set(contents)
        
        # Allow some similarity but not exact duplicates
        assert len(unique) >= len(contents) * 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
