from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class BudgetAction:
    type: str
    amount: Decimal
    from_campaign: Optional[str] = None
    to_campaign: Optional[str] = None


@dataclass(frozen=True, slots=True)
class LedgerSummary:
    total_spent: Decimal
    total_revenue: Decimal
    net_pnl: Decimal
    unreconciled_count: int


@dataclass(frozen=True, slots=True)
class OrchestratorDecision:
    decision_id: str
    timestamp: datetime
    action_type: str
    target_product: Optional[str]
    target_creative: Optional[str]
    budget_action: Optional[BudgetAction]
    reason_codes: Tuple[str, ...]
    confidence: str
    risk_status: str
    blocking_conditions: Tuple[str, ...]
    next_step: str
    artifact_path: str


@dataclass(frozen=True, slots=True)
class OutcomeData:
    roas: Optional[Decimal] = None
    spend: Optional[Decimal] = None
    conversions: Optional[int] = None
    notes: Optional[str] = None


@dataclass(frozen=True, slots=True)
class DecisionEntry:
    decision_id: str
    timestamp: datetime
    orchestrator_version: str
    vault_learning_remaining: Decimal
    vault_operational_remaining: Decimal
    active_campaigns: int
    active_products: int
    reconcile_status: str
    circuit_breaker_status: str
    action_type: str
    target_product: Optional[str]
    target_creative: Optional[str]
    budget_action_type: Optional[str]
    budget_action_amount: Decimal
    reason_codes: Tuple[str, ...]
    confidence: str
    risk_status: str
    blocking_conditions: Tuple[str, ...]
    outcome_recorded: bool = False
    outcome_timestamp: Optional[datetime] = None
    outcome_roas: Optional[Decimal] = None
    outcome_spend: Optional[Decimal] = None
    outcome_conversions: Optional[int] = None
    outcome_notes: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CreativeVariant:
    variant_id: str
    product_id: str
    created_at: datetime
    angle: str
    hook: str
    format: str
    asset_path: str
    status: str = "untested"
    spend_total: Decimal = Decimal("0")
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    revenue: Decimal = Decimal("0")
    roas: Optional[Decimal] = None
    ctr: Optional[Decimal] = None
    cpa: Optional[Decimal] = None
    decision_ids: Tuple[str, ...] = field(default_factory=tuple)
    kill_reason: Optional[str] = None
    kill_decision_id: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    product_id: str
    variants: Tuple[CreativeVariant, ...]
    best_variant_id: Optional[str]
    worst_variant_id: Optional[str]


ALLOWED_ACTION_TYPES = frozenset({
    "launch_test",
    "scale_up",
    "scale_down",
    "kill_campaign",
    "pause_all",
    "rotate_creative",
    "add_product",
    "hold",
    "emergency_stop",
})

ALLOWED_VARIANT_STATUS = frozenset({
    "untested",
    "active",
    "paused",
    "killed",
    "winner",
})