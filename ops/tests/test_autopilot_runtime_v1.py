from __future__ import annotations

from decimal import Decimal

from ops.autopilot_runtime_v1 import AutopilotRuntimeRequest, run_autopilot_runtime


class FakeVault:
    def __init__(self, initial_budget: Decimal) -> None:
        self.remaining = Decimal(initial_budget)
        self.calls: list[tuple[Decimal, str]] = []

    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        amount = Decimal(amount)
        self.calls.append((amount, budget_type))
        if amount <= self.remaining:
            self.remaining -= amount
            return True
        return False


class ExplodingVault:
    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        raise RuntimeError("vault exploded")


def test_runtime_returns_create_campaign_mapping_for_test_action() -> None:
    result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-new",
            final_decision="approved",
            current_roas=0.9,
            spend=Decimal("0"),
            requested_budget=Decimal("10"),
            correlation_id="corr-runtime-test",
        ),
        vault=FakeVault(Decimal("50")),
    )

    assert result.product_id == "p-new"
    assert result.correlation_id == "corr-runtime-test"
    assert result.action == "test"
    assert result.publisher_action == "create_campaign"
    assert result.reason == "test_within_budget"
    assert result.capital_reason == "approved"
    assert result.allocated_budget == Decimal("10")


def test_runtime_preserves_vault_error_reason_fidelity() -> None:
    result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-vault-error",
            final_decision="approved",
            current_roas=1.1,
            spend=Decimal("20"),
            requested_budget=Decimal("15"),
            correlation_id="corr-runtime-vault-error",
        ),
        vault=ExplodingVault(),
    )

    assert result.action == "hold"
    assert result.publisher_action is None
    assert result.reason == "vault_error_from_vault"
    assert result.capital_reason == "vault_error"
    assert result.correlation_id == "corr-runtime-vault-error"


def test_runtime_rejected_product_does_not_publish() -> None:
    result = run_autopilot_runtime(
        AutopilotRuntimeRequest(
            product_id="p-rejected",
            final_decision="rejected",
            current_roas=2.0,
            spend=Decimal("50"),
            requested_budget=Decimal("20"),
            correlation_id="corr-runtime-rejected",
        ),
        vault=FakeVault(Decimal("999")),
    )

    assert result.action == "hold"
    assert result.publisher_action is None
    assert result.reason == "not_approved_by_buyer"
    assert result.capital_reason is None
