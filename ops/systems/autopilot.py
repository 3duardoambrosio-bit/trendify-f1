from dataclasses import dataclass
from typing import Iterable, List

from ops.catalog_pipeline import CatalogItemResult


@dataclass
class ActionPlanItem:
    """
    Representa qué hacer con un producto después del análisis F1.
    """
    product_id: str
    action: str  # "launch_test" | "skip" | "review"
    reason: str
    test_budget: float = 0.0
    composite_score: float | None = None
    quality_score: float | None = None


@dataclass
class ActionPlanSummary:
    total_products: int
    to_launch: int
    to_skip: int
    to_review: int
    total_test_budget: float


def build_action_plan(items: Iterable[CatalogItemResult]) -> List[ActionPlanItem]:
    """
    Traduce los resultados de catálogo en un plan de acción simple.

    Reglas básicas (v1):
    - approved + allocated_test_budget > 0 -> launch_test
    - rejected -> skip
    - unknown -> review
    """
    plan: List[ActionPlanItem] = []

    for item in items:
        action: str
        reason: str
        test_budget = float(getattr(item, "allocated_test_budget", 0.0) or 0.0)

        comp = getattr(item, "composite_score", None)
        qual = getattr(item, "quality_score", None)

        if item.final_decision == "approved" and test_budget > 0:
            action = "launch_test"
            reason = "approved_with_budget"
        elif item.final_decision == "rejected":
            action = "skip"
            reason = "rejected"
            test_budget = 0.0
        else:
            action = "review"
            reason = f"decision_{item.final_decision}"
            # en review no asignamos budget todavía
            test_budget = 0.0

        plan.append(
            ActionPlanItem(
                product_id=item.product_id,
                action=action,
                reason=reason,
                test_budget=test_budget,
                composite_score=comp,
                quality_score=qual,
            )
        )

    return plan


def summarize_action_plan(plan: Iterable[ActionPlanItem]) -> ActionPlanSummary:
    """
    Saca métricas rápidas del action plan.
    """
    total = 0
    to_launch = 0
    to_skip = 0
    to_review = 0
    total_budget = 0.0

    for p in plan:
        total += 1
        total_budget += float(p.test_budget or 0.0)

        if p.action == "launch_test":
            to_launch += 1
        elif p.action == "skip":
            to_skip += 1
        else:
            to_review += 1

    return ActionPlanSummary(
        total_products=total,
        to_launch=to_launch,
        to_skip=to_skip,
        to_review=to_review,
        total_test_budget=total_budget,
    )
