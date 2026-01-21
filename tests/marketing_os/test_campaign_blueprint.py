# tests/marketing_os/test_campaign_blueprint.py
import pytest
from synapse.marketing_os.campaign_blueprint import (
    BlueprintGenerator, CampaignBlueprint, Platform, Objective,
    TargetingConfig, quick_blueprint
)


@pytest.fixture
def generator():
    return BlueprintGenerator(default_budget=50.0)


@pytest.fixture
def sample_kit():
    return {
        "hooks": [
            {"content": "Hook 1 test", "variant_id": "H1", "quality_score": 0.8},
            {"content": "Hook 2 test", "variant_id": "H2", "quality_score": 0.7},
        ],
        "primary_texts": [
            {"content": "Primary text 1", "quality_score": 0.75},
        ],
        "scripts_15s": [
            {"content": "Script 15s 1", "variant_id": "S1", "quality_score": 0.8},
        ],
    }


class TestBlueprintGenerator:
    def test_generate_meta_blueprint(self, generator, sample_kit):
        bp = generator.generate_meta_blueprint("34357", "Audifonos M10", sample_kit)
        assert isinstance(bp, CampaignBlueprint)
        assert bp.platform == Platform.META
        assert bp.product_id == "34357"
    
    def test_meta_has_adsets(self, generator, sample_kit):
        bp = generator.generate_meta_blueprint("34357", "Audifonos M10", sample_kit)
        assert len(bp.adsets) >= 1
    
    def test_meta_has_creatives(self, generator, sample_kit):
        bp = generator.generate_meta_blueprint("34357", "Audifonos M10", sample_kit)
        total_creatives = sum(len(adset.creatives) for adset in bp.adsets)
        assert total_creatives > 0
    
    def test_meta_has_utm(self, generator, sample_kit):
        bp = generator.generate_meta_blueprint("34357", "Audifonos M10", sample_kit)
        assert "utm_source" in bp.utm_params
        assert bp.utm_params["utm_source"] == "meta"
    
    def test_generate_tiktok_blueprint(self, generator, sample_kit):
        bp = generator.generate_tiktok_blueprint("34357", "Audifonos M10", sample_kit)
        assert bp.platform == Platform.TIKTOK
    
    def test_tiktok_uses_scripts(self, generator, sample_kit):
        bp = generator.generate_tiktok_blueprint("34357", "Audifonos M10", sample_kit)
        creatives = bp.adsets[0].creatives
        assert any(c.content_type == "script_15s" for c in creatives)
    
    def test_generate_all_platforms(self, generator, sample_kit):
        blueprints = generator.generate_all_platforms("34357", "Audifonos", sample_kit, 100)
        assert "meta" in blueprints
        assert "tiktok" in blueprints
    
    def test_budget_split(self, generator, sample_kit):
        blueprints = generator.generate_all_platforms("34357", "Audifonos", sample_kit, 100)
        assert blueprints["meta"].total_budget_usd == 60.0
        assert blueprints["tiktok"].total_budget_usd == 40.0


class TestCampaignBlueprint:
    def test_to_dict(self, generator, sample_kit):
        bp = generator.generate_meta_blueprint("34357", "Test", sample_kit)
        d = bp.to_dict()
        assert d["platform"] == "meta"
        assert d["objective"] == "conversions"
    
    def test_to_json(self, generator, sample_kit):
        bp = generator.generate_meta_blueprint("34357", "Test", sample_kit)
        j = bp.to_json()
        assert '"platform": "meta"' in j


class TestTargetingConfig:
    def test_default_targeting(self):
        t = TargetingConfig()
        assert "MX" in t.geo
        assert t.age_min == 18
    
    def test_custom_targeting(self):
        t = TargetingConfig(geo=["MX", "CO"], age_min=25, age_max=45)
        assert "CO" in t.geo
        assert t.age_min == 25


class TestQuickBlueprint:
    def test_quick_blueprint_meta(self):
        bp = quick_blueprint("123", "Test", ["Hook 1", "Hook 2"], "meta", 30)
        assert bp.platform == Platform.META
        assert bp.total_budget_usd == 30
    
    def test_quick_blueprint_tiktok(self):
        bp = quick_blueprint("123", "Test", ["Hook 1"], "tiktok", 25)
        assert bp.platform == Platform.TIKTOK
