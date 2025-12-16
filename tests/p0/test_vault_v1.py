from __future__ import annotations

from decimal import Decimal

import pytest

from vault.v1 import BudgetType, SpendRequest, Vault, VaultConfig


def test_vault_reserve_protected() -> None:
    v = Vault(VaultConfig(total=Decimal("100.00")))
    d = v.request_spend(SpendRequest(product_id="r004", amount=Decimal("1"), budget=BudgetType.RESERVE, reason="no"))
    assert d.allowed is False
    assert d.reason == "RESERVE_PROTECTED"


def test_vault_learning_spend_and_insufficient() -> None:
    v = Vault(VaultConfig(total=Decimal("100.00")))
    # learning = 30
    ok = v.request_spend(SpendRequest("r004", Decimal("10"), BudgetType.LEARNING, "test"))
    assert ok.allowed is True
    bad = v.request_spend(SpendRequest("r004", Decimal("25"), BudgetType.LEARNING, "too much"))
    assert bad.allowed is False
    assert bad.reason == "INSUFFICIENT_LEARNING"


def test_vault_operational_spend_and_insufficient() -> None:
    v = Vault(VaultConfig(total=Decimal("100.00")))
    # operational = 55
    ok = v.request_spend(SpendRequest("r004", Decimal("50"), BudgetType.OPERATIONAL, "ops"))
    assert ok.allowed is True
    bad = v.request_spend(SpendRequest("r004", Decimal("10"), BudgetType.OPERATIONAL, "too much"))
    assert bad.allowed is False
    assert bad.reason == "INSUFFICIENT_OPERATIONAL"