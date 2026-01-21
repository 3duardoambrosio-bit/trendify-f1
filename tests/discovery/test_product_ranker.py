# tests/discovery/test_product_ranker.py
import pytest
from synapse.discovery import ProductRanker, ProductScore, ProductCandidate, rank_products


@pytest.fixture
def sample_candidates():
    return [
        ProductCandidate(product_id="1", title="Audifonos Pro", category="audio", price=599, cost=180, rating=4.7, reviews=150, match_score=0.8),
        ProductCandidate(product_id="2", title="Audifonos Basic", category="audio", price=299, cost=150, rating=4.0, reviews=50, match_score=0.5),
        ProductCandidate(product_id="3", title="Audifonos Budget", category="audio", price=199, cost=120, rating=3.5, reviews=20, match_score=0.3),
        ProductCandidate(product_id="4", title="Audifonos Premium", category="audio", price=899, cost=270, rating=4.8, reviews=200, match_score=0.9),
        ProductCandidate(product_id="5", title="Audifonos Mid", category="audio", price=450, cost=180, rating=4.2, reviews=80, match_score=0.6),
    ]


class TestProductRanker:
    def test_rank_returns_result(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates)
        assert len(result.ranked_products) > 0
    
    def test_rank_respects_top_n(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates, top_n=3)
        assert len(result.ranked_products) <= 3
    
    def test_products_are_sorted_by_score(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates)
        scores = [p.total_score for p in result.ranked_products]
        assert scores == sorted(scores, reverse=True)
    
    def test_products_have_ranks(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates)
        ranks = [p.rank for p in result.ranked_products]
        assert ranks == list(range(1, len(ranks) + 1))
    
    def test_high_margin_scores_higher(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates)
        high_margin = [p for p in result.ranked_products if p.margin_percent > 60]
        low_margin = [p for p in result.ranked_products if p.margin_percent < 50]
        if high_margin and low_margin:
            assert high_margin[0].margin_score > low_margin[0].margin_score
    
    def test_score_has_all_components(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates)
        for p in result.ranked_products:
            assert 0 <= p.margin_score <= 1
            assert 0 <= p.demand_score <= 1
            assert 0 <= p.quality_score <= 1
            assert 0 <= p.total_score <= 1
    
    def test_products_have_recommendation(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates)
        for p in result.ranked_products:
            assert p.recommendation != ""
    
    def test_min_score_filter(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates, min_score=0.5)
        for p in result.ranked_products:
            assert p.total_score >= 0.5
    
    def test_custom_weights(self, sample_candidates):
        weights = {"margin": 0.5, "demand": 0.2, "quality": 0.2, "differentiation": 0.05, "risk": 0.05}
        ranker = ProductRanker(weights=weights)
        result = ranker.rank(sample_candidates)
        assert result.weights["margin"] == 0.5


class TestProductScore:
    def test_strengths_populated(self, sample_candidates):
        ranker = ProductRanker()
        result = ranker.rank(sample_candidates)
        high_scorer = result.ranked_products[0]
        assert len(high_scorer.strengths) > 0 or len(high_scorer.weaknesses) > 0


class TestRankProducts:
    def test_rank_products_helper(self, sample_candidates):
        ranked = rank_products(sample_candidates, top_n=3)
        assert len(ranked) == 3
        assert all(isinstance(p, ProductScore) for p in ranked)
