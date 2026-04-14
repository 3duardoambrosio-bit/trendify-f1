# V3GAP:D-04_spend_pacing_alert

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ops.spend_gateway_v1 import ProductCaps, SpendGateway
from synapse.ledger_ndjson import read_events
from vault.v1 import BudgetType, SpendRequest, Vault, VaultConfig


def _ledger(path: Path) -> SimpleNamespace:
    return SimpleNamespace(path=path)


def test_gateway_caps_day1_and_total(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "events.ndjson")
    v = Vault(VaultConfig(total=Decimal("100.00")))
    g = SpendGateway(
        vault=v,
        ledger=ledger,
        caps=ProductCaps(max_total_learning=Decimal("30"), max_day1_learning=Decimal("10")),
        idempotency_db_path=tmp_path / "idempotency.sqlite3",
    )

    d1 = g.request(
        SpendRequest("r004", Decimal("11"), BudgetType.LEARNING, "d1", day=1),
        idempotency_key="t_caps_d1_exceed",
    )
    assert d1.allowed is False
    assert d1.reason == "CAP_LEARNING_DAY1"

    ok = g.request(
        SpendRequest("r004", Decimal("10"), BudgetType.LEARNING, "d1 ok", day=1),
        idempotency_key="t_caps_d1_ok",
    )
    assert ok.allowed is True

    ok2 = g.request(
        SpendRequest("r004", Decimal("20"), BudgetType.LEARNING, "total ok", day=2),
        idempotency_key="t_caps_total_ok2",
    )
    assert ok2.allowed is True

    bad = g.request(
        SpendRequest("r004", Decimal("1"), BudgetType.LEARNING, "exceed", day=3),
        idempotency_key="t_caps_total_exceed",
    )
    assert bad.allowed is False
    assert bad.reason == "CAP_LEARNING_TOTAL"

    rows = read_events(ledger.path)
    assert any(r["event_type"] == "SPEND_DENIED" for r in rows)
    assert any(r["event_type"] == "SPEND_APPROVED" for r in rows)


def test_gateway_reserve_attempt_logged(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "events.ndjson")
    v = Vault(VaultConfig(total=Decimal("100.00")))
    g = SpendGateway(
        vault=v,
        ledger=ledger,
        idempotency_db_path=tmp_path / "idempotency.sqlite3",
    )

    d = g.request(
        SpendRequest("r003", Decimal("5"), BudgetType.RESERVE, "nope", day=1),
        idempotency_key="t_reserve_attempt",
    )
    assert d.allowed is False
    assert d.reason == "RESERVE_PROTECTED"

    rows = read_events(ledger.path)
    assert rows[-1]["event_type"] == "SPEND_DENIED"
    assert rows[-1]["payload"]["reason"] == "RESERVE_PROTECTED"