from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from core.ledger import Ledger
from ops.spend_gateway_v1 import SpendGateway, ProductCaps
from vault.v1 import BudgetType, SpendRequest, Vault, VaultConfig


def test_gateway_caps_day1_and_total(tmp_path: Path) -> None:
    ledger = Ledger(path=str(tmp_path / "events.ndjson"))
    v = Vault(VaultConfig(total=Decimal("100.00")))
    g = SpendGateway(vault=v, ledger=ledger, caps=ProductCaps(max_total_learning=Decimal("30"), max_day1_learning=Decimal("10")))

    # day 1 cap
    d1 = g.request(SpendRequest("r004", Decimal("11"), BudgetType.LEARNING, "d1", day=1))
    assert d1.allowed is False
    assert d1.reason == "CAP_LEARNING_DAY1"

    # approve within day1
    ok = g.request(SpendRequest("r004", Decimal("10"), BudgetType.LEARNING, "d1 ok", day=1))
    assert ok.allowed is True

    # total cap
    ok2 = g.request(SpendRequest("r004", Decimal("20"), BudgetType.LEARNING, "total ok", day=2))
    assert ok2.allowed is True

    # would exceed total
    bad = g.request(SpendRequest("r004", Decimal("1"), BudgetType.LEARNING, "exceed", day=3))
    assert bad.allowed is False
    assert bad.reason == "CAP_LEARNING_TOTAL"

    # ledger has approvals/denials
    rows = list(ledger.iter_events())
    assert any(r["event_type"] == "SPEND_DENIED" for r in rows)
    assert any(r["event_type"] == "SPEND_APPROVED" for r in rows)


def test_gateway_reserve_attempt_logged(tmp_path: Path) -> None:
    ledger = Ledger(path=str(tmp_path / "events.ndjson"))
    v = Vault(VaultConfig(total=Decimal("100.00")))
    g = SpendGateway(vault=v, ledger=ledger)

    d = g.request(SpendRequest("r003", Decimal("5"), BudgetType.RESERVE, "nope", day=1))
    assert d.allowed is False
    assert d.reason == "RESERVE_PROTECTED"

    rows = list(ledger.iter_events())
    assert rows[-1]["event_type"] == "SPEND_DENIED"
    assert rows[-1]["payload"]["reason"] == "RESERVE_PROTECTED"