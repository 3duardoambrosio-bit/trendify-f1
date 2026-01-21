# tests/marketing_os/test_experiment_engine.py
import pytest
from synapse.marketing_os.experiment_engine import (
    ExperimentEngine, ExperimentMetrics, ExperimentDecision,
    Decision, StopLossConfig, quick_evaluate
)


@pytest.fixture
def engine():
    return ExperimentEngine()


@pytest.fixture
def good_metrics():
    return ExperimentMetrics(
        experiment_id="exp001",
        product_id="34357",
        variant_id="H1_dolor",
        spend_usd=50,
        hours_running=48,
        impressions=5000,
        clicks=75,
        conversions=5,
        revenue_usd=500,
        video_views=4000,
        video_3s_views=1000,
    )


@pytest.fixture
def bad_metrics():
    return ExperimentMetrics(
        experiment_id="exp002",
        product_id="34357",
        variant_id="H2_status",
        spend_usd=100,
        hours_running=48,
        impressions=10000,
        clicks=20,
        conversions=0,
        video_views=5000,
        video_3s_views=2000,
    )


class TestExperimentMetrics:
    def test_ctr_calculation(self, good_metrics):
        assert good_metrics.ctr == 1.5
    
    def test_cvr_calculation(self, good_metrics):
        assert abs(good_metrics.cvr - 6.67) < 0.1
    
    def test_cpa_calculation(self, good_metrics):
        assert good_metrics.cpa == 10.0
    
    def test_roas_calculation(self, good_metrics):
        assert good_metrics.roas == 10.0
    
    def test_hook_rate_calculation(self, good_metrics):
        assert good_metrics.hook_rate == 20.0
    
    def test_zero_division_protection(self):
        empty = ExperimentMetrics("e", "p", "v")
        assert empty.ctr == 0
        assert empty.cvr == 0
        assert empty.cpa == float("inf")
        assert empty.roas == 0


class TestExperimentEngine:
    def test_insufficient_spend_continues(self, engine):
        metrics = ExperimentMetrics("e", "p", "v", spend_usd=5, hours_running=48)
        decision = engine.evaluate(metrics, target_cpa=100)
        assert decision.decision == Decision.CONTINUE
        assert "Insufficient spend" in decision.reasons[0]
    
    def test_insufficient_time_continues(self, engine):
        metrics = ExperimentMetrics("e", "p", "v", spend_usd=50, hours_running=12)
        decision = engine.evaluate(metrics, target_cpa=100)
        assert decision.decision == Decision.CONTINUE
        assert "Insufficient time" in decision.reasons[0]
    
    def test_high_cpa_kills(self, engine):
        metrics = ExperimentMetrics(
            "e", "p", "v",
            spend_usd=600, hours_running=48,
            impressions=5000, clicks=100, conversions=2,
            video_views=4000, video_3s_views=1000
        )
        decision = engine.evaluate(metrics, target_cpa=100)
        assert decision.decision == Decision.KILL
    
    def test_low_ctr_kills(self, engine):
        metrics = ExperimentMetrics(
            "e", "p", "v",
            spend_usd=50, hours_running=48,
            impressions=5000, clicks=10, conversions=0,
            video_views=4000, video_3s_views=1000
        )
        decision = engine.evaluate(metrics, target_cpa=100)
        assert decision.decision == Decision.KILL
    
    def test_no_conversions_kills(self, engine, bad_metrics):
        decision = engine.evaluate(bad_metrics, target_cpa=50)
        assert decision.decision == Decision.KILL
    
    def test_good_metrics_scales(self, engine, good_metrics):
        decision = engine.evaluate(good_metrics, target_cpa=15)
        assert decision.decision in [Decision.SCALE_UP, Decision.GRADUATE]
    
    def test_excellent_metrics_graduates(self, engine):
        metrics = ExperimentMetrics(
            "e", "p", "v",
            spend_usd=200, hours_running=72,
            impressions=20000, clicks=400, conversions=15,
            revenue_usd=1500,
            video_views=15000, video_3s_views=5000
        )
        decision = engine.evaluate(metrics, target_cpa=20)
        assert decision.decision == Decision.GRADUATE
    
    def test_decision_has_confidence(self, engine, good_metrics):
        decision = engine.evaluate(good_metrics, target_cpa=100)
        assert 0 <= decision.confidence <= 1
    
    def test_decision_has_snapshot(self, engine, good_metrics):
        decision = engine.evaluate(good_metrics, target_cpa=100)
        assert "spend_usd" in decision.metrics_snapshot


class TestUTMGeneration:
    def test_generate_utm(self, engine):
        utm = engine.generate_utm(
            product_id="34357",
            hook_id="H1",
            angle="dolor",
            format="hands_only",
            variant="A"
        )
        assert utm["utm_source"] == "paid"
        assert utm["utm_campaign"] == "P34357"


class TestBatchEvaluate:
    def test_batch_groups_decisions(self, engine):
        experiments = [
            ExperimentMetrics("e1", "p", "v", spend_usd=50, hours_running=48, impressions=5000, clicks=100, conversions=5, video_3s_views=1000),
            ExperimentMetrics("e2", "p", "v", spend_usd=100, hours_running=48, impressions=5000, clicks=10, conversions=0, video_3s_views=1000),
            ExperimentMetrics("e3", "p", "v", spend_usd=5, hours_running=48),
        ]
        result = engine.batch_evaluate(experiments, target_cpa=20)
        assert "kill" in result
        assert "continue" in result


class TestQuickEvaluate:
    def test_quick_evaluate_works(self):
        decision = quick_evaluate(
            spend=50, impressions=5000, clicks=100, conversions=3, target_cpa=50,
        )
        assert isinstance(decision, ExperimentDecision)
