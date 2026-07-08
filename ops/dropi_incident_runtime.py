from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, Optional

from synapse.integrations.dropi.payment_guarantee_bridge import (
    build_dropi_payment_guarantee_bridge,
)

DropiIncidentAction = Literal["hold", "review", "open_case"]


@dataclass(frozen=True)
class DropiIncidentContext:
    order_id: str
    payment_method: str
    issue_type: str
    order_created_at: datetime
    customer_paid_at: Optional[datetime] = None
    supplier_payment_delay_hours: int = 24
    resolution_preference: str = "replacement"
    channel: str = "ops_runtime"
    metadata: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class DropiIncidentDecision:
    action: DropiIncidentAction
    reason: str
    trace_id: str
    bridge_status: str
    supplier_payment_ready: bool
    guarantee_case_ready: bool
    order_id: str
    bridge: Mapping[str, Any]


class DropiIncidentRuntime:
    def __init__(self, ledger: Any, event_type: str = "dropi_guarantee_bridge_decided") -> None:
        self._ledger = ledger
        self._event_type = event_type

    @staticmethod
    def _classify(bridge_status: str) -> tuple[DropiIncidentAction, str]:
        if bridge_status == "guarantee_case_ready":
            return "open_case", "ready_for_dropi_case"
        if bridge_status == "unsupported_issue_type":
            return "review", "unsupported_issue_type"
        return "hold", bridge_status

    def decide(self, ctx: DropiIncidentContext) -> DropiIncidentDecision:
        bridge = build_dropi_payment_guarantee_bridge(
            ctx.payment_method,
            order_id=ctx.order_id,
            issue_type=ctx.issue_type,
            order_created_at=ctx.order_created_at,
            customer_paid_at=ctx.customer_paid_at,
            supplier_payment_delay_hours=ctx.supplier_payment_delay_hours,
            resolution_preference=ctx.resolution_preference,
            channel=ctx.channel,
            metadata=ctx.metadata,
        )

        bridge_status = str(bridge["bridge_status"])
        action, reason = self._classify(bridge_status)
        trace_id = f"dropi_bridge:{bridge['order_id']}:{bridge.get('issue_type') or 'unknown'}"

        meta: dict[str, Any] = {
            "entity_type": "order",
            "entity_id": str(bridge["order_id"]),
            "trace_id": trace_id,
            "order_id": bridge["order_id"],
            "payment_method": bridge["payment_method"],
            "issue_type": bridge.get("issue_type"),
            "bridge_status": bridge_status,
            "supplier_payment_ready": bool(bridge["supplier_payment_ready"]),
            "guarantee_case_ready": bool(bridge["guarantee_case_ready"]),
            "action": action,
            "reason": reason,
        }

        if ctx.metadata is not None:
            meta["metadata"] = dict(ctx.metadata)

        self._ledger.write(
            self._event_type,
            "0.00",
            memo=trace_id,
            meta=meta,
        )

        return DropiIncidentDecision(
            action=action,
            reason=reason,
            trace_id=trace_id,
            bridge_status=bridge_status,
            supplier_payment_ready=bool(bridge["supplier_payment_ready"]),
            guarantee_case_ready=bool(bridge["guarantee_case_ready"]),
            order_id=str(bridge["order_id"]),
            bridge=bridge,
        )