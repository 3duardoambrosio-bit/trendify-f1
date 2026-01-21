# tests/discovery/test_niche_selector.py
import pytest
import tempfile
from pathlib import Path
from synapse.discovery import (
    NicheSelector, NicheProfile, NicheCategory, NicheRisk,
    CompetitionLevel, NICHE_CATALOG, list_niches, get_niche_keywords
)


@pytest.fixture
def temp_selector():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield NicheSelector(config_dir=tmpdir)


class TestNicheCatalog:
    def test_catalog_has_niches(self):
        assert len(NICHE_CATALOG) >= 10
    
    def test_all_niches_have_keywords(self):
        for niche in NICHE_CATALOG.values():
            assert len(niche.keywords) > 0
    
    def test_all_niches_have_opportunity_score(self):
        for niche in NICHE_CATALOG.values():
            assert 0 <= niche.opportunity_score <= 1
    
    def test_audio_personal_exists(self):
        assert "audio_personal" in NICHE_CATALOG


class TestNicheSelector:
    def test_list_all(self, temp_selector):
        niches = temp_selector.list_all()
        assert len(niches) >= 10
    
    def test_list_by_category(self, temp_selector):
        electronics = temp_selector.list_by_category(NicheCategory.ELECTRONICS)
        assert len(electronics) >= 3
    
    def test_list_by_opportunity(self, temp_selector):
        top = temp_selector.list_by_opportunity(min_score=0.65)
        assert len(top) >= 5
    
    def test_list_low_risk(self, temp_selector):
        low_risk = temp_selector.list_low_risk()
        assert len(low_risk) >= 5
    
    def test_get_niche(self, temp_selector):
        niche = temp_selector.get("audio_personal")
        assert niche is not None
    
    def test_select_niche(self, temp_selector):
        selection = temp_selector.select("audio_personal", reason="Test")
        assert selection.niche_id == "audio_personal"
    
    def test_select_persists(self, temp_selector):
        temp_selector.select("audio_personal", reason="Test")
        assert temp_selector.get_current() is not None
    
    def test_clear_selection(self, temp_selector):
        temp_selector.select("audio_personal", reason="Test")
        temp_selector.clear_selection()
        assert temp_selector.get_current() is None
    
    def test_compare_niches(self, temp_selector):
        comparison = temp_selector.compare(["audio_personal", "led_lights"])
        assert len(comparison) == 2
    
    def test_recommend(self, temp_selector):
        recommended = temp_selector.recommend(max_risk=NicheRisk.LOW)
        assert len(recommended) >= 3


class TestNicheHelpers:
    def test_list_niches(self):
        niches = list_niches()
        assert "audio_personal" in niches
    
    def test_get_niche_keywords(self):
        keywords = get_niche_keywords("audio_personal")
        assert "audifono" in keywords
