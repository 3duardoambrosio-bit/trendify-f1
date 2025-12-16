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