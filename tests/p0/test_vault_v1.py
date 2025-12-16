from decimal import Decimal
from vault.vault_v1 import BudgetPool, VaultV1


def test_reserve_is_protected() -> None:
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    r = v.request_spend(pool="reserve", product_id="r004", amount=Decimal("1"), day=1)
    assert r.allowed is False
    assert r.reason == "RESERVE_PROTECTED"


def test_day1_cap_enforced() -> None:
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    ok = v.request_spend(pool="learning", product_id="r004", amount=Decimal("10"), day=1)
    assert ok.allowed is True
    nope = v.request_spend(pool="learning", product_id="r004", amount=Decimal("0.01"), day=1)
    assert nope.allowed is False
    assert nope.reason == "DAY1_CAP_REACHED"


def test_product_total_cap_enforced() -> None:
    v = VaultV1(
        learning=BudgetPool("learning", Decimal("30")),
        operational=BudgetPool("operational", Decimal("55")),
        reserve=BudgetPool("reserve", Decimal("15")),
    )
    ok1 = v.request_spend(pool="learning", product_id="r004", amount=Decimal("10"), day=1)
    ok2 = v.request_spend(pool="learning", product_id="r004", amount=Decimal("20"), day=2)
    assert ok1.allowed and ok2.allowed
    nope = v.request_spend(pool="learning", product_id="r004", amount=Decimal("0.01"), day=3)
    assert nope.allowed is False
    assert nope.reason == "PRODUCT_TOTAL_CAP_REACHED"