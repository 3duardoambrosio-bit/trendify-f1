from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hypothesis import given, strategies as st

from synapse.safety.integrations.vault_gate import VaultGateConfig, request_spend_with_gate
from synapse.safety.limits import RiskLimits


BUDGET = st.integers(min_value=1, max_value=10_000)
AMOUNT = st.integers(min_value=0, max_value=10_000)
BUCKET = st.sampled_from(["learning", "operational", "reserve"])


@dataclass
class FakeVault:
    total_budget: Decimal
    calls: int = 0

    def request_spend(self, amount: Decimal, *, bucket: str):
        self.calls += 1
        return {"allowed": True, "amount": str(amount), "bucket": bucket}


@given(BUDGET, AMOUNT, BUCKET)
def test_request_spend_with_gate_executes_only_when_allowed(budget_i: int, amount_i: int, bucket: str) -> None:
    v = FakeVault(total_budget=Decimal(str(budget_i)))
    cfg = VaultGateConfig(limits=RiskLimits())
    amt = Decimal(str(amount_i))

    r = request_spend_with_gate(vault=v, amount=amt, bucket=bucket, cfg=cfg)

    if r.executed:
        assert v.calls == 1
        assert r.error is None
    else:
        assert v.calls == 0
        assert r.error is not None
