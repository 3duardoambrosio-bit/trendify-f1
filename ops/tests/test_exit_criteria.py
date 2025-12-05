from ops.exit_criteria import (
    ExitCriteriaEngine,
    ProductPerformanceSnapshot,
    Verdict,
    evaluate_product_exit,
)


def make_snapshot(
    *,
    product_id: str = "prod_1",
    days_running: int = 0,
    total_spend: float = 0.0,
    total_revenue: float = 0.0,
    quality_score: float = 0.8,
) -> ProductPerformanceSnapshot:
    return ProductPerformanceSnapshot(
        product_id=product_id,
        days_running=days_running,
        total_spend=total_spend,
        total_revenue=total_revenue,
        quality_score=quality_score,
    )


def test_continue_when_insufficient_data():
    engine = ExitCriteriaEngine(
        min_days_for_decision=2,
        min_spend_for_decision=10.0,
    )

    snap = make_snapshot(days_running=1, total_spend=5.0, total_revenue=0.0)

    decision = engine.evaluate_product(snap)

    assert decision.verdict == Verdict.CONTINUE
    assert decision.reason == "insufficient_data"


def test_kill_when_zero_roas_after_threshold():
    engine = ExitCriteriaEngine(
        zero_roas_hard_kill_spend=30.0,
        min_days_for_decision=1,
        min_spend_for_decision=10.0,
    )

    snap = make_snapshot(days_running=3, total_spend=40.0, total_revenue=0.0)

    decision = engine.evaluate_product(snap)

    assert decision.verdict == Verdict.KILL
    assert decision.reason == "zero_roas_after_threshold"


def test_kill_when_roas_below_minimum():
    engine = ExitCriteriaEngine(
        min_roas_to_continue=1.2,
        min_days_for_decision=1,
        min_spend_for_decision=10.0,
    )

    # ROAS = 30 / 50 = 0.6  < 1.2
    snap = make_snapshot(days_running=3, total_spend=50.0, total_revenue=30.0)

    decision = engine.evaluate_product(snap)

    assert decision.verdict == Verdict.KILL
    assert decision.reason == "roas_below_minimum"


def test_scale_when_roas_high_and_quality_good():
    engine = ExitCriteriaEngine(
        scale_roas_threshold=2.0,
        scale_quality_threshold=0.8,
        min_days_for_decision=1,
        min_spend_for_decision=10.0,
    )

    # ROAS = 150 / 50 = 3.0  (alto) con calidad 0.9
    snap = make_snapshot(
        days_running=3,
        total_spend=50.0,
        total_revenue=150.0,
        quality_score=0.9,
    )

    decision = engine.evaluate_product(snap)

    assert decision.verdict == Verdict.SCALE
    assert decision.reason == "scale_winner"


def test_continue_when_middle_zone():
    engine = ExitCriteriaEngine(
        min_roas_to_continue=1.2,
        scale_roas_threshold=2.0,
        min_days_for_decision=1,
        min_spend_for_decision=10.0,
    )

    # ROAS = 40 / 30 ≈ 1.33  (aceptable pero no ganador)
    snap = make_snapshot(
        days_running=3,
        total_spend=30.0,
        total_revenue=40.0,
        quality_score=0.75,
    )

    decision = engine.evaluate_product(snap)

    assert decision.verdict == Verdict.CONTINUE
    assert decision.reason == "keep_testing"


def test_module_helper_evaluate_product_exit_uses_default_engine():
    snap = make_snapshot(
        days_running=3,
        total_spend=20.0,
        total_revenue=30.0,
        quality_score=0.85,
    )

    decision = evaluate_product_exit(snap)

    assert isinstance(decision.verdict, Verdict)
    # No validamos reason exacto aquí, solo que no truena.
