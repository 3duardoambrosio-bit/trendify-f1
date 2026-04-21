from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal, Optional

from .autopilot_v2 import AutopilotContext, AutopilotV2

PublisherAction = Literal["create_campaign", "pause_campaign"]


@dataclass(frozen=True)
class AutopilotRuntimeRequest:
    product_id: str
    final_decision: str
    current_roas: float
    spend: Decimal
    requested_budget: Decimal
    correlation_id: str = ""


@dataclass(frozen=True)
class AutopilotRuntimeResult:
    product_id: str
    correlation_id: str
    action: str
    allocated_budget: Decimal
    reason: str
    final_decision: str
    current_roas: float
    spend: Decimal
    requested_budget: Decimal
    capital_reason: Optional[str]
    kill_action: Optional[str]
    publisher_action: Optional[PublisherAction]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allocated_budget"] = str(self.allocated_budget)
        data["spend"] = str(self.spend)
        data["requested_budget"] = str(self.requested_budget)
        return data


def _map_publisher_action(action: str) -> Optional[PublisherAction]:
    if action in {"test", "scale"}:
        return "create_campaign"
    if action == "pause":
        return "pause_campaign"
    return None


def run_autopilot_runtime(
    request: AutopilotRuntimeRequest,
    *,
    vault: object,
    default_budget_type: str = "learning",
) -> AutopilotRuntimeResult:
    autopilot = AutopilotV2(vault=vault, default_budget_type=default_budget_type)

    ctx = AutopilotContext(
        product_id=request.product_id,
        final_decision=request.final_decision,
        current_roas=request.current_roas,
        spend=Decimal(request.spend),
        requested_budget=Decimal(request.requested_budget),
    )

    decision = autopilot.decide(ctx)

    capital_reason = decision.capital_decision.reason if decision.capital_decision is not None else None
    kill_action = decision.kill_decision.action if decision.kill_decision is not None else None

    return AutopilotRuntimeResult(
        product_id=request.product_id,
        correlation_id=request.correlation_id,
        action=decision.action,
        allocated_budget=decision.allocated_budget,
        reason=decision.reason,
        final_decision=request.final_decision,
        current_roas=request.current_roas,
        spend=Decimal(request.spend),
        requested_budget=Decimal(request.requested_budget),
        capital_reason=capital_reason,
        kill_action=kill_action,
        publisher_action=_map_publisher_action(decision.action),
    )
