from __future__ import annotations

import dataclasses
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from infra.vault import VaultSnapshot

from synapse.core.models import DecisionEntry, OrchestratorDecision, OutcomeData


JOURNAL_VERSION = "sbrain-capa-a-v1"


def _dt_to_str(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _str_to_dt(value: Optional[str]) -> Optional[datetime]:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(value)


def _entry_to_dict(entry: DecisionEntry) -> dict:
    return {
        "decision_id": entry.decision_id,
        "timestamp": entry.timestamp.isoformat(),
        "orchestrator_version": entry.orchestrator_version,
        "vault_learning_remaining": str(entry.vault_learning_remaining),
        "vault_operational_remaining": str(entry.vault_operational_remaining),
        "active_campaigns": entry.active_campaigns,
        "active_products": entry.active_products,
        "reconcile_status": entry.reconcile_status,
        "circuit_breaker_status": entry.circuit_breaker_status,
        "action_type": entry.action_type,
        "target_product": entry.target_product,
        "target_creative": entry.target_creative,
        "budget_action_type": entry.budget_action_type,
        "budget_action_amount": str(entry.budget_action_amount),
        "reason_codes": list(entry.reason_codes),
        "confidence": entry.confidence,
        "risk_status": entry.risk_status,
        "blocking_conditions": list(entry.blocking_conditions),
        "outcome_recorded": entry.outcome_recorded,
        "outcome_timestamp": _dt_to_str(entry.outcome_timestamp),
        "outcome_roas": None if entry.outcome_roas is None else str(entry.outcome_roas),
        "outcome_spend": None if entry.outcome_spend is None else str(entry.outcome_spend),
        "outcome_conversions": entry.outcome_conversions,
        "outcome_notes": entry.outcome_notes,
    }


def _entry_from_dict(data: dict) -> DecisionEntry:
    return DecisionEntry(
        decision_id=data["decision_id"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        orchestrator_version=data["orchestrator_version"],
        vault_learning_remaining=Decimal(data["vault_learning_remaining"]),
        vault_operational_remaining=Decimal(data["vault_operational_remaining"]),
        active_campaigns=int(data["active_campaigns"]),
        active_products=int(data["active_products"]),
        reconcile_status=data["reconcile_status"],
        circuit_breaker_status=data["circuit_breaker_status"],
        action_type=data["action_type"],
        target_product=data.get("target_product"),
        target_creative=data.get("target_creative"),
        budget_action_type=data.get("budget_action_type"),
        budget_action_amount=Decimal(data["budget_action_amount"]),
        reason_codes=tuple(data.get("reason_codes", [])),
        confidence=data["confidence"],
        risk_status=data["risk_status"],
        blocking_conditions=tuple(data.get("blocking_conditions", [])),
        outcome_recorded=bool(data.get("outcome_recorded", False)),
        outcome_timestamp=_str_to_dt(data.get("outcome_timestamp")),
        outcome_roas=None if data.get("outcome_roas") is None else Decimal(data["outcome_roas"]),
        outcome_spend=None if data.get("outcome_spend") is None else Decimal(data["outcome_spend"]),
        outcome_conversions=data.get("outcome_conversions"),
        outcome_notes=data.get("outcome_notes"),
    )


def _learning_remaining(vault: VaultSnapshot) -> Decimal:
    if hasattr(vault, "learning_remaining"):
        value = getattr(vault, "learning_remaining")
        return value() if callable(value) else value
    return vault.learning_budget - vault.spent_learning


def _operational_remaining(vault: VaultSnapshot) -> Decimal:
    if hasattr(vault, "operational_remaining"):
        value = getattr(vault, "operational_remaining")
        return value() if callable(value) else value
    return vault.operational_budget - vault.spent_operational


class DecisionJournal:
    def __init__(self, path: str = "data/journal/decisions.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        decision: OrchestratorDecision,
        vault: VaultSnapshot,
        active_campaigns: int,
        active_products: int,
        reconcile_status: str,
        circuit_breaker_status: str,
    ) -> DecisionEntry:
        entry = DecisionEntry(
            decision_id=decision.decision_id,
            timestamp=decision.timestamp,
            orchestrator_version=JOURNAL_VERSION,
            vault_learning_remaining=_learning_remaining(vault),
            vault_operational_remaining=_operational_remaining(vault),
            active_campaigns=active_campaigns,
            active_products=active_products,
            reconcile_status=reconcile_status,
            circuit_breaker_status=circuit_breaker_status,
            action_type=decision.action_type,
            target_product=decision.target_product,
            target_creative=decision.target_creative,
            budget_action_type=None if decision.budget_action is None else decision.budget_action.type,
            budget_action_amount=Decimal("0") if decision.budget_action is None else decision.budget_action.amount,
            reason_codes=tuple(decision.reason_codes),
            confidence=decision.confidence,
            risk_status=decision.risk_status,
            blocking_conditions=tuple(decision.blocking_conditions),
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_entry_to_dict(entry), ensure_ascii=False) + "\n")
        return entry

    def record_outcome(self, decision_id: str, outcome: OutcomeData) -> DecisionEntry:
        entries = self.query(last_n=None)
        updated = None
        for idx, entry in enumerate(entries):
            if entry.decision_id == decision_id:
                updated = replace(
                    entry,
                    outcome_recorded=True,
                    outcome_timestamp=datetime.now(timezone.utc),
                    outcome_roas=outcome.roas,
                    outcome_spend=outcome.spend,
                    outcome_conversions=outcome.conversions,
                    outcome_notes=outcome.notes,
                )
                entries[idx] = updated
                break
        if updated is None:
            raise ValueError(f"decision_id not found: {decision_id}")
        with self.path.open("w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(_entry_to_dict(entry), ensure_ascii=False) + "\n")
        return updated

    def query(self, product_id: Optional[str] = None, last_n: Optional[int] = 10) -> list[DecisionEntry]:
        if not self.path.exists():
            return []
        out: list[DecisionEntry] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entry = _entry_from_dict(json.loads(line))
                if product_id is not None and entry.target_product != product_id:
                    continue
                out.append(entry)
        if last_n is None:
            return out
        return out[-last_n:]

    def replay(self, decision_id: str) -> DecisionEntry:
        for entry in self.query(last_n=None):
            if entry.decision_id == decision_id:
                return entry
        raise ValueError(f"decision_id not found: {decision_id}")

    def count(self) -> int:
        return len(self.query(last_n=None))