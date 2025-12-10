from ops.catalog_pipeline import CatalogItemResult
from ops.systems.autopilot import (
    ActionPlanItem,
    ActionPlanSummary,
    build_action_plan,
    summarize_action_plan,
)


def _make_item(
    product_id: str,
    final_decision: str,
    buyer_decision: str | None,
    composite: float | None,
    quality: float | None,
    budget: float,
    capital_reason: str,
) -> CatalogItemResult:
    return CatalogItemResult(
        product_id=product_id,
        final_decision=final_decision,
        buyer_decision=buyer_decision,
        composite_score=composite,
        quality_score=quality,
        allocated_test_budget=budget,
        capital_reason=capital_reason,
    )


def test_build_action_plan_basic() -> None:
    items = [
        _make_item("p1", "approved", "approved", 0.8, 0.9, 10.0, "ok"),
        _make_item("p2", "rejected", "rejected", 0.3, 0.4, 0.0, "not_approved"),
        _make_item("p3", "unknown", None, None, None, 0.0, "not_evaluated"),
    ]

    plan = build_action_plan(items)
    assert len(plan) == 3

    p1 = next(p for p in plan if p.product_id == "p1")
    p2 = next(p for p in plan if p.product_id == "p2")
    p3 = next(p for p in plan if p.product_id == "p3")

    assert p1.action == "launch_test"
    assert p1.test_budget == 10.0

    assert p2.action == "skip"
    assert p2.test_budget == 0.0

    assert p3.action == "review"
    assert p3.test_budget == 0.0


def test_summarize_action_plan_counts_and_budget() -> None:
    plan = [
        ActionPlanItem(
            product_id="p1",
            action="launch_test",
            reason="approved_with_budget",
            test_budget=10.0,
        ),
        ActionPlanItem(
            product_id="p2",
            action="skip",
            reason="rejected",
            test_budget=0.0,
        ),
        ActionPlanItem(
            product_id="p3",
            action="review",
            reason="decision_unknown",
            test_budget=0.0,
        ),
    ]

    summary = summarize_action_plan(plan)

    assert isinstance(summary, ActionPlanSummary)
    assert summary.total_products == 3
    assert summary.to_launch == 1
    assert summary.to_skip == 1
    assert summary.to_review == 1
    assert summary.total_test_budget == 10.0
