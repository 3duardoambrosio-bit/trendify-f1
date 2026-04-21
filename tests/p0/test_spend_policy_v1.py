from decimal import Decimal
from vault.vault_v1 import VaultV1, BudgetPool
from vault.cashflow_v1 import CashFlowState
from ops.spend_policy_v1 import SpendPolicyV1


def test_policy_denies_on_cashflow_even_if_vault_allows():
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    cash = CashFlowState(available_cash=Decimal("5"), safety_buffer_cash=Decimal("5"))
    p = SpendPolicyV1(v, cash)
    d = p.request(pool="learning", product_id="r004", amount=Decimal("1"), day=1)
    assert d.allowed is False
    assert d.reason == "CASHFLOW_GUARD"


def test_policy_respects_vault_specific_reason():
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    cash = CashFlowState(available_cash=Decimal("999"), safety_buffer_cash=Decimal("0"))
    p = SpendPolicyV1(v, cash)
    d1 = p.request(pool="learning", product_id="r004", amount=Decimal("10"), day=1)
    assert d1.allowed is True
    d2 = p.request(pool="learning", product_id="r004", amount=Decimal("0.01"), day=1)  # day1 cap
    assert d2.allowed is False
    assert d2.reason in ("DAY1_CAP_REACHED", "PRODUCT_TOTAL_CAP_REACHED", "INSUFFICIENT_POOL_FUNDS")

class _FakeLedger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


def test_cashflow_guard_rolls_back_learning_state_and_emits_audit():
    ledger = _FakeLedger()
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    cash = CashFlowState(available_cash=Decimal("5"), safety_buffer_cash=Decimal("5"))
    p = SpendPolicyV1(v, cash, ledger=ledger)

    d = p.request(pool="learning", product_id="r004", amount=Decimal("1"), day=1)

    assert d.allowed is False
    assert d.reason == "CASHFLOW_GUARD"
    assert v.learning.spent == Decimal("0")
    assert v._learning_spent_by_product.get("r004", Decimal("0")) == Decimal("0")
    assert [event_type for event_type, _ in ledger.events] == ["SPEND_ROLLED_BACK", "SPEND_DENIED"]
    assert ledger.events[0][1]["reason"] == "CASHFLOW_GUARD_ROLLBACK"
    assert ledger.events[0][1]["vault_reason"] == "APPROVED"
    assert ledger.events[0][1]["cashflow_ok"] is False
    assert ledger.events[1][1]["reason"] == "CASHFLOW_GUARD"
    assert ledger.events[1][1]["vault_reason"] == "APPROVED"
    assert ledger.events[1][1]["cashflow_ok"] is False


def test_cashflow_guard_rolls_back_operational_state_exactly():
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    cash = CashFlowState(available_cash=Decimal("5"), safety_buffer_cash=Decimal("5"))
    p = SpendPolicyV1(v, cash)

    d = p.request(pool="operational", product_id="r004", amount=Decimal("1"), day=1)

    assert d.allowed is False
    assert d.reason == "CASHFLOW_GUARD"
    assert v.operational.spent == Decimal("0")
    assert v._learning_spent_by_product == {}


def test_private_rollback_clamps_learning_tracking_to_zero():
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    cash = CashFlowState(available_cash=Decimal("999"), safety_buffer_cash=Decimal("0"))
    p = SpendPolicyV1(v, cash)

    p._rollback_vault(pool="learning", amount=Decimal("5"), product_id="ghost")

    assert v.learning.spent == Decimal("0")
    assert v._learning_spent_by_product.get("ghost", Decimal("0")) == Decimal("0")

def test_policy_approved_emits_audit_payload_with_reason_and_flags():
    ledger = _FakeLedger()
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    cash = CashFlowState(available_cash=Decimal("999"), safety_buffer_cash=Decimal("0"))
    p = SpendPolicyV1(v, cash, ledger=ledger)

    d = p.request(pool="learning", product_id="r004", amount=Decimal("1"), day=1)

    assert d.allowed is True
    assert d.reason == "APPROVED"
    assert d.vault_reason == "APPROVED"
    assert d.cashflow_ok is True
    assert [event_type for event_type, _ in ledger.events] == ["SPEND_APPROVED"]
    assert ledger.events[0][1]["reason"] == "APPROVED"
    assert ledger.events[0][1]["vault_reason"] == "APPROVED"
    assert ledger.events[0][1]["cashflow_ok"] is True


def test_policy_vault_denial_emits_audit_payload_with_vault_reason():
    ledger = _FakeLedger()
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    cash = CashFlowState(available_cash=Decimal("999"), safety_buffer_cash=Decimal("0"))
    p = SpendPolicyV1(v, cash, ledger=ledger)

    p.request(pool="learning", product_id="r004", amount=Decimal("10"), day=1)
    d = p.request(pool="learning", product_id="r004", amount=Decimal("0.01"), day=1)

    assert d.allowed is False
    assert d.reason in ("DAY1_CAP_REACHED", "PRODUCT_TOTAL_CAP_REACHED", "INSUFFICIENT_POOL_FUNDS")
    assert d.vault_reason == d.reason
    assert d.cashflow_ok is True
    assert ledger.events[-1][0] == "SPEND_DENIED"
    assert ledger.events[-1][1]["reason"] == d.reason
    assert ledger.events[-1][1]["vault_reason"] == d.reason
    assert ledger.events[-1][1]["cashflow_ok"] is True

