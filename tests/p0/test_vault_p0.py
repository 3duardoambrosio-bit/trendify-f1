from decimal import Decimal
from vault.vault_p0 import VaultP0


def test_vault_allocations_sum_to_total():
    v = VaultP0(total_budget=Decimal("100.00"))
    assert v.total == Decimal("100.00")
    assert (v.learning.total + v.operational.total + v.reserve.total) == Decimal("100.00")


def test_reserve_is_protected():
    v = VaultP0(total_budget=Decimal("100.00"))
    d = v.request_spend(pool="reserve", amount=Decimal("1.00"))
    assert d.allowed is False
    assert d.reason == "reserve_protected"


def test_cannot_overspend_pool():
    v = VaultP0(total_budget=Decimal("100.00"))
    d = v.request_spend(pool="learning", amount=v.learning.total + Decimal("0.01"))
    assert d.allowed is False
    assert d.reason == "insufficient_funds"


def test_amount_must_be_positive():
    v = VaultP0(total_budget=Decimal("100.00"))
    d = v.request_spend(pool="learning", amount=Decimal("0.00"))
    assert d.allowed is False
    assert d.reason == "amount_must_be_positive"