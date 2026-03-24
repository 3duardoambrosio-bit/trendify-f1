from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from infra.vault import VaultSnapshot
from synapse.core.decision_journal import DecisionJournal
from synapse.core.models import BudgetAction, OutcomeData, OrchestratorDecision, utc_now


def _vault():
    return VaultSnapshot(
        total_budget=Decimal("300"),
        learning_budget=Decimal("150"),
        operational_budget=Decimal("100"),
        reserve_budget=Decimal("50"),
        spent_learning=Decimal("10"),
        spent_operational=Decimal("20"),
    )


def _decision(decision_id="D1", product="P1"):
    return OrchestratorDecision(
        decision_id=decision_id,
        timestamp=utc_now(),
        action_type="launch_test",
        target_product=product,
        target_creative=None,
        budget_action=BudgetAction(type="allocate", amount=Decimal("30")),
        reason_codes=("budget_available",),
        confidence="medium",
        risk_status="green",
        blocking_conditions=(),
        next_step="launch",
        artifact_path="data/decisions/test.json",
    )


class TestDecisionJournal:
    def test_append_and_count(self, tmp_path):
        j = DecisionJournal(str(tmp_path / "decisions.jsonl"))
        j.append(_decision(), _vault(), 1, 1, "green", "closed")
        assert j.count() == 1

    def test_query_by_product(self, tmp_path):
        j = DecisionJournal(str(tmp_path / "decisions.jsonl"))
        j.append(_decision("D1", "P1"), _vault(), 1, 1, "green", "closed")
        j.append(_decision("D2", "P2"), _vault(), 1, 1, "green", "closed")
        rows = j.query(product_id="P2", last_n=None)
        assert len(rows) == 1
        assert rows[0].target_product == "P2"

    def test_record_outcome(self, tmp_path):
        j = DecisionJournal(str(tmp_path / "decisions.jsonl"))
        j.append(_decision("D1", "P1"), _vault(), 1, 1, "green", "closed")
        updated = j.record_outcome("D1", OutcomeData(roas=Decimal("2.2"), spend=Decimal("30"), conversions=2, notes="ok"))
        assert updated.outcome_recorded is True
        assert updated.outcome_roas == Decimal("2.2")

    def test_replay(self, tmp_path):
        j = DecisionJournal(str(tmp_path / "decisions.jsonl"))
        j.append(_decision("D1", "P1"), _vault(), 1, 1, "green", "closed")
        row = j.replay("D1")
        assert row.decision_id == "D1"

    def test_missing_outcome_raises(self, tmp_path):
        j = DecisionJournal(str(tmp_path / "decisions.jsonl"))
        with pytest.raises(ValueError):
            j.record_outcome("MISSING", OutcomeData())

    def test_entry_is_frozen(self, tmp_path):
        j = DecisionJournal(str(tmp_path / "decisions.jsonl"))
        entry = j.append(_decision(), _vault(), 1, 1, "green", "closed")
        with pytest.raises(FrozenInstanceError):
            entry.action_type = "x"