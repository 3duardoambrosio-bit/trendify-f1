from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional

from config.feature_flags import FeatureFlags
from infra.vault import VaultSnapshot
from synapse.discovery.catalog_scanner import ProductCandidate

from synapse.core.models import (
    ALLOWED_ACTION_TYPES,
    BudgetAction,
    CreativeVariant,
    LedgerSummary,
    OrchestratorDecision,
    utc_now,
)

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


ORCHESTRATOR_VERSION = "sbrain-capa-a-v2"


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_safe(x) for x in value]
    if isinstance(value, list):
        return [_json_safe(x) for x in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return value


def _write_decision_artifact(path: str, decision: OrchestratorDecision) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_json_safe(asdict(decision)), fh, indent=2, ensure_ascii=False)


def _load_thresholds(path: str = "config/thresholds.yaml") -> dict:
    defaults = {
        "budget_floor": Decimal("30"),
        "launch_max": Decimal("100"),
        "launch_fraction": Decimal("0.30"),
        "scale_fraction": Decimal("0.50"),
        "kill_roas_below": Decimal("1.0"),
        "kill_min_spend": Decimal("50"),
        "kill_min_days": 2,
        "scale_roas_at_or_above": Decimal("2.0"),
        "rotate_outperform_ratio": Decimal("2.0"),
        "max_unreconciled": 3,
    }
    p = Path(path)
    if yaml is None or not p.exists():
        return defaults
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    section = raw.get("orchestrator", {})
    merged = dict(defaults)
    for key, value in section.items():
        if key in {"kill_min_days", "max_unreconciled"}:
            merged[key] = int(value)
        else:
            merged[key] = _to_decimal(value)
    return merged


def _learning_remaining(vault: VaultSnapshot) -> Decimal:
    attr = getattr(vault, "learning_remaining", None)
    if attr is not None:
        return _to_decimal(attr() if callable(attr) else attr)
    return _to_decimal(vault.learning_budget) - _to_decimal(vault.spent_learning)


def _operational_remaining(vault: VaultSnapshot) -> Decimal:
    attr = getattr(vault, "operational_remaining", None)
    if attr is not None:
        return _to_decimal(attr() if callable(attr) else attr)
    return _to_decimal(vault.operational_budget) - _to_decimal(vault.spent_operational)


def read_ops_tick(path: str = "data/run/ops_tick.json") -> dict:
    p = Path(path)
    if not p.exists():
        return {
            "status": "MISSING",
            "marker": "MISSING",
            "reconcile_status": "red",
            "alerts_pending": 0,
            "last_run": None,
            "readonly_invariant_ok": False,
            "checks": {},
        }

    with p.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    checks = payload.get("checks") or {}
    reconcile_gate = checks.get("reconcile_preflight", None)

    if reconcile_gate is None:
        reconcile_status = "red"
    elif isinstance(reconcile_gate, bool):
        reconcile_status = "green" if reconcile_gate else "red"
    elif isinstance(reconcile_gate, dict):
        blocked = reconcile_gate.get("blocked", None)
        gate_status = str(reconcile_gate.get("status", "")).strip().lower()
        gate_reason = str(reconcile_gate.get("reason", "")).strip().lower()

        if blocked is True:
            reconcile_status = "red"
        elif gate_status in {"ok", "pass", "green"}:
            reconcile_status = "green"
        elif gate_status == "skipped":
            reconcile_status = "yellow"
        elif gate_reason in {"env_vars_not_set", "env_var_not_set"}:
            reconcile_status = "yellow"
        elif blocked is False:
            reconcile_status = "green"
        else:
            reconcile_status = "red"
    else:
        reconcile_status = "red"

    alerts_pending = 0
    steps = payload.get("steps") or []
    alerts_pending = sum(1 for step in steps if str(step.get("returncode", 0)) not in {"0", "None"})

    return {
        "status": payload.get("status", "UNKNOWN"),
        "marker": payload.get("marker", "UNKNOWN"),
        "reconcile_status": reconcile_status,
        "alerts_pending": alerts_pending,
        "last_run": payload.get("ts_utc") or payload.get("ts"),
        "readonly_invariant_ok": bool(checks.get("readonly_invariant_ok", False)),
        "checks": checks,
    }


def build_ledger_summary(rows: Iterable[Any]) -> LedgerSummary:
    total_spent = Decimal("0")
    total_revenue = Decimal("0")
    unreconciled_count = 0

    expense_hints = ("spend", "expense", "cost", "fee", "refund", "charge")
    revenue_hints = ("sale", "revenue", "income", "order", "payment", "capture")

    for row in rows:
        if isinstance(row, dict):
            kind = str(row.get("kind", ""))
            amount = _to_decimal(row.get("amount", "0"))
            meta = row.get("meta", {}) or {}
        else:
            kind = str(getattr(row, "kind", ""))
            amount = _to_decimal(getattr(row, "amount", "0"))
            meta = getattr(row, "meta", {}) or {}

        kind_l = kind.lower()
        abs_amount = abs(amount)

        if any(token in kind_l for token in expense_hints):
            total_spent += abs_amount
        elif any(token in kind_l for token in revenue_hints):
            total_revenue += abs_amount
        else:
            if amount < 0:
                total_spent += abs_amount
            else:
                total_revenue += abs_amount

        if isinstance(meta, dict) and meta.get("reconciled") is False:
            unreconciled_count += 1

    return LedgerSummary(
        total_spent=total_spent,
        total_revenue=total_revenue,
        net_pnl=total_revenue - total_spent,
        unreconciled_count=unreconciled_count,
    )


def _decision(
    action_type: str,
    target_product: Optional[str],
    target_creative: Optional[str],
    budget_action: Optional[BudgetAction],
    reason_codes: list[str],
    confidence: str,
    risk_status: str,
    blocking_conditions: list[str],
    next_step: str,
    decisions_dir: str,
) -> OrchestratorDecision:
    if action_type not in ALLOWED_ACTION_TYPES:
        raise ValueError(f"invalid action_type: {action_type}")
    decision_id = str(uuid.uuid4())
    artifact_path = str(Path(decisions_dir) / f"{decision_id}.json")
    decision = OrchestratorDecision(
        decision_id=decision_id,
        timestamp=utc_now(),
        action_type=action_type,
        target_product=target_product,
        target_creative=target_creative,
        budget_action=budget_action,
        reason_codes=tuple(reason_codes),
        confidence=confidence,
        risk_status=risk_status,
        blocking_conditions=tuple(blocking_conditions),
        next_step=next_step,
        artifact_path=artifact_path,
    )
    _write_decision_artifact(artifact_path, decision)
    return decision


def decide(
    vault: VaultSnapshot,
    discovery_shortlist: list[ProductCandidate],
    creative_registry: list[CreativeVariant],
    campaign_snapshots: list[Any],
    breaker_status: str = "closed",
    kill_switch_active: bool = False,
    feature_flags=None,
    ops_tick_path: str = "data/run/ops_tick.json",
    ledger_rows: Optional[Iterable[Any]] = None,
    decisions_dir: str = "data/decisions",
    thresholds_path: str = "config/thresholds.yaml",
) -> list[OrchestratorDecision]:
    thresholds = _load_thresholds(thresholds_path)
    Path(decisions_dir).mkdir(parents=True, exist_ok=True)

    ops_tick = read_ops_tick(ops_tick_path)
    ledger_summary = build_ledger_summary([] if ledger_rows is None else ledger_rows)

    learning_remaining = _learning_remaining(vault)
    operational_remaining = _operational_remaining(vault)
    available_budget = learning_remaining

    flags = feature_flags
    if flags is None:
        try:
            flags = FeatureFlags()
        except Exception:
            flags = None

    decisions: list[OrchestratorDecision] = []

    if kill_switch_active or str(breaker_status).lower() == "open":
        reasons = []
        if kill_switch_active:
            reasons.append("kill_switch_active")
        if str(breaker_status).lower() == "open":
            reasons.append("circuit_breaker_open")
        decisions.append(_decision(
            action_type="emergency_stop",
            target_product=None,
            target_creative=None,
            budget_action=None,
            reason_codes=reasons,
            confidence="high",
            risk_status="red",
            blocking_conditions=reasons,
            next_step="Stop all writes and resolve safety state before continuing.",
            decisions_dir=decisions_dir,
        ))
        return decisions

    if ops_tick["reconcile_status"] == "red" or ledger_summary.unreconciled_count > int(thresholds["max_unreconciled"]):
        decisions.append(_decision(
            action_type="pause_all",
            target_product=None,
            target_creative=None,
            budget_action=None,
            reason_codes=["reconcile_integrity"],
            confidence="high",
            risk_status="red",
            blocking_conditions=["reconcile_red"],
            next_step="Do not spend. Repair reconciliation path first.",
            decisions_dir=decisions_dir,
        ))
        return decisions

    if available_budget < thresholds["budget_floor"]:
        decisions.append(_decision(
            action_type="hold",
            target_product=None,
            target_creative=None,
            budget_action=None,
            reason_codes=["budget_exhausted"],
            confidence="high",
            risk_status="yellow",
            blocking_conditions=[],
            next_step="Wait. Learning budget below floor.",
            decisions_dir=decisions_dir,
        ))
        return decisions

    spend_block = []
    if flags is not None and getattr(flags, "spend_real_money", False) is False:
        spend_block = ["spend_real_money_disabled"]

    for snap in campaign_snapshots:
        status = str(getattr(snap, "status", "")).lower()
        if status != "active":
            continue

        roas = getattr(snap, "roas", None)
        roas = None if roas is None else _to_decimal(roas)
        spend_today = _to_decimal(getattr(snap, "spend_today", "0"))
        days_active = int(getattr(snap, "days_active", 0))
        product_id = getattr(snap, "product_id", None)
        variant_id = getattr(snap, "variant_id", None)
        campaign_id = getattr(snap, "campaign_id", None)

        if roas is not None and roas < thresholds["kill_roas_below"] and spend_today >= thresholds["kill_min_spend"] and days_active >= int(thresholds["kill_min_days"]):
            decisions.append(_decision(
                action_type="kill_campaign",
                target_product=product_id,
                target_creative=variant_id,
                budget_action=BudgetAction(type="freeze", amount=Decimal("0"), from_campaign=campaign_id, to_campaign=None),
                reason_codes=["roas_below_threshold"],
                confidence="high",
                risk_status="red",
                blocking_conditions=[],
                next_step=f"Kill campaign {campaign_id}.",
                decisions_dir=decisions_dir,
            ))
            continue

        if roas is not None and roas >= thresholds["scale_roas_at_or_above"]:
            raw_alloc = available_budget * thresholds["scale_fraction"]
            alloc = raw_alloc if raw_alloc > Decimal("0") else Decimal("0")
            decisions.append(_decision(
                action_type="scale_up",
                target_product=product_id,
                target_creative=variant_id,
                budget_action=BudgetAction(type="allocate", amount=alloc, from_campaign=None, to_campaign=campaign_id),
                reason_codes=["roas_above_threshold", "budget_available"],
                confidence="medium",
                risk_status="green",
                blocking_conditions=spend_block,
                next_step=f"Scale campaign {campaign_id} by controlled budget.",
                decisions_dir=decisions_dir,
            ))
            continue

        if roas is not None and roas >= thresholds["kill_roas_below"] and roas < thresholds["scale_roas_at_or_above"]:
            decisions.append(_decision(
                action_type="hold",
                target_product=product_id,
                target_creative=variant_id,
                budget_action=None,
                reason_codes=["performance_inconclusive"],
                confidence="low",
                risk_status="yellow",
                blocking_conditions=[],
                next_step=f"Keep observing campaign {campaign_id}.",
                decisions_dir=decisions_dir,
            ))

    active_product_ids = {
        str(getattr(snap, "product_id", ""))
        for snap in campaign_snapshots
        if str(getattr(snap, "status", "")).lower() == "active"
    }

    if discovery_shortlist:
        ordered_shortlist = sorted(
            discovery_shortlist,
            key=lambda item: (float(getattr(item, "match_score", 0.0)), float(getattr(item, "margin_percent", 0.0))),
            reverse=True,
        )
        for candidate in ordered_shortlist:
            if str(getattr(candidate, "product_id", "")) not in active_product_ids:
                launch_amount = min(thresholds["launch_max"], available_budget * thresholds["launch_fraction"])
                decisions.append(_decision(
                    action_type="launch_test",
                    target_product=str(getattr(candidate, "product_id", "")),
                    target_creative=None,
                    budget_action=BudgetAction(type="allocate", amount=launch_amount, from_campaign=None, to_campaign=None),
                    reason_codes=["budget_available", "untested_product_available"],
                    confidence="medium",
                    risk_status="green",
                    blocking_conditions=spend_block,
                    next_step=f"Launch controlled test for {getattr(candidate, 'product_id', '')}.",
                    decisions_dir=decisions_dir,
                ))
                break

    product_to_variants: dict[str, list[CreativeVariant]] = {}
    for item in creative_registry:
        if item.roas is None:
            continue
        product_to_variants.setdefault(item.product_id, []).append(item)

    for product_id, variants in product_to_variants.items():
        if len(variants) < 2:
            continue

        best = max(variants, key=lambda item: _to_decimal(item.roas))
        peer_variants = [item for item in variants if item.variant_id != best.variant_id]

        if not peer_variants:
            continue

        peer_avg_roas = (
            sum((_to_decimal(item.roas) for item in peer_variants), Decimal("0"))
            / Decimal(len(peer_variants))
        )

        if peer_avg_roas <= Decimal("0"):
            continue

        if _to_decimal(best.roas) >= peer_avg_roas * thresholds["rotate_outperform_ratio"]:
            decisions.append(_decision(
                action_type="rotate_creative",
                target_product=product_id,
                target_creative=best.variant_id,
                budget_action=None,
                reason_codes=["variant_outperforming"],
                confidence="medium",
                risk_status="green",
                blocking_conditions=[],
                next_step=f"Promote creative {best.variant_id} and pause weaker peers.",
                decisions_dir=decisions_dir,
            ))

    if not decisions:
        decisions.append(_decision(
            action_type="hold",
            target_product=None,
            target_creative=None,
            budget_action=None,
            reason_codes=["no_actionable_signal"],
            confidence="low",
            risk_status="yellow",
            blocking_conditions=[],
            next_step="No action. Continue collecting signal.",
            decisions_dir=decisions_dir,
        ))

    return decisions