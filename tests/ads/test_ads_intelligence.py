# tests/ads/test_ads_intelligence.py
import pytest

from synapse.ads import (
    MetaAdsIntelligence,
    TikTokAdsIntelligence,
    GoogleAdsIntelligence,
    calculate_test_budget,
    estimate_results,
)


class TestMetaAdsIntelligence:
    def test_benchmarks_exist(self):
        assert MetaAdsIntelligence.BENCHMARKS_MX["ctr_avg"] > 0

    def test_get_recommended_structure(self):
        structure = MetaAdsIntelligence.get_recommended_structure(50)
        assert structure["campaign"]["daily_budget_usd"] == 50.0
        assert len(structure["ad_sets"]) >= 2

    def test_get_audience_for_niche(self):
        audience = MetaAdsIntelligence.get_audience_for_niche("audio_personal")
        assert audience.name != ""
        assert len(audience.interests) > 0

    def test_get_testing_framework(self):
        framework = MetaAdsIntelligence.get_testing_framework()
        assert "phase_1_hooks" in framework
        assert "phase_2_angles" in framework

    def test_calculate_budget_allocation(self):
        allocation = MetaAdsIntelligence.calculate_budget_allocation(100, "testing")
        assert sum(allocation.values()) == 100.0


class TestTikTokAdsIntelligence:
    def test_benchmarks_exist(self):
        assert TikTokAdsIntelligence.BENCHMARKS_MX["cpm_avg"] > 0

    def test_faceless_formats(self):
        assert len(TikTokAdsIntelligence.FACELESS_FORMATS) >= 5

    def test_get_ad_structure(self):
        structure = TikTokAdsIntelligence.get_ad_structure(30)
        assert structure["campaign"]["daily_budget_usd"] == 30.0

    def test_get_creative_guidelines(self):
        guidelines = TikTokAdsIntelligence.get_creative_guidelines("audio_personal")
        assert guidelines["captions"] == "required"


class TestGoogleAdsIntelligence:
    def test_remarketing_audiences(self):
        assert "cart_abandoners" in GoogleAdsIntelligence.REMARKETING_AUDIENCES

    def test_get_remarketing_structure(self):
        structure = GoogleAdsIntelligence.get_remarketing_structure(20)
        assert structure["strategy"] == "remarketing"


class TestHelpers:
    def test_calculate_test_budget(self):
        budget = calculate_test_budget(cpa_target=15, tests_count=5, confidence_conversions=3)
        assert budget == 225.0  # 15 * 3 * 5

    def test_estimate_results(self):
        results = estimate_results(budget=100, cpm=5, ctr=1.0, cvr=2.0)
        assert results["impressions"] == 20000.0
        assert results["clicks"] == 200.0
        assert results["conversions"] == 4.0
