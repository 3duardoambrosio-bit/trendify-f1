from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ops.spend_gateway_v1 import SpendGateway
from synapse.ledger_ndjson import read_events


class _Vault:
    def __init__(self) -> None:
        self.calls = 0

    def request_spend(self, _req):
        self.calls += 1
        return SimpleNamespace(allowed=True, reason="OK")


def _req(*, amount: str, request_id: str = "req-1"):
    return SimpleNamespace(
        amount=Decimal(amount),
        budget="operational",
        budget_type="operational",
        product_id="sku-1",
        day=1,
        request_id=request_id,
        channel="meta",
        country="MX",
        currency="MXN",
        data_freshness_minutes=0,
        tracking_freshness_minutes=0,
        heartbeat_age_minutes=0,
    )


def test_spend_gateway_uses_sqlite_idempotency_and_logs_once(tmp_path: Path) -> None:
    vault = _Vault()
    ledger = SimpleNamespace(path=tmp_path / "events.ndjson")
    gateway = SpendGateway(vault=vault, ledger=ledger, idempotency_db_path=tmp_path / "idempotency.sqlite3")

    first = gateway.request(_req(amount="100.00"), idempotency_key="idem-1")
    second = gateway.request(_req(amount="100.00"), idempotency_key="idem-1")

    assert first.allowed is True
    assert second.allowed is True
    assert vault.calls == 1

    events = read_events(ledger.path)
    assert len(events) == 1
    assert events[0]["event_type"] == "SPEND_APPROVED"
    assert events[0]["clock_source_id"] == "synapse.time_utc.v1"


def test_spend_gateway_blocks_outside_odd_by_default(tmp_path: Path) -> None:
    vault = _Vault()
    ledger = SimpleNamespace(path=tmp_path / "events.ndjson")
    gateway = SpendGateway(vault=vault, ledger=ledger, idempotency_db_path=tmp_path / "idempotency.sqlite3")

    decision = gateway.request(_req(amount="2000.00", request_id="req-2"), idempotency_key="idem-2")

    assert decision.allowed is False
    assert decision.reason.startswith("ODD_OUTSIDE:")
    assert vault.calls == 0

    events = read_events(ledger.path)
    assert len(events) == 1
    assert events[0]["event_type"] == "SPEND_BLOCKED_SAFETY"

def test_spend_gateway_conflict_is_fail_closed_and_logs_denial(tmp_path: Path) -> None:
    vault = _Vault()
    ledger = SimpleNamespace(path=tmp_path / "events.ndjson")
    gateway = SpendGateway(vault=vault, ledger=ledger, idempotency_db_path=tmp_path / "idempotency.sqlite3")

    with patch(
        "ops.spend_gateway_v1.execute_once",
        return_value={"status": "CONFLICT", "response": None},
    ):
        decision = gateway.request(_req(amount="100.00", request_id="req-conflict"), idempotency_key="idem-conflict")

    assert decision.allowed is False
    assert decision.reason == "IDEMPOTENCY_CONFLICT"
    assert vault.calls == 0

    events = read_events(ledger.path)
    assert len(events) == 1
    assert events[0]["event_type"] == "SPEND_DENIED"
    assert events[0]["payload"]["reason"] == "IDEMPOTENCY_CONFLICT"


def test_spend_gateway_in_flight_is_fail_closed_and_logs_denial(tmp_path: Path) -> None:
    vault = _Vault()
    ledger = SimpleNamespace(path=tmp_path / "events.ndjson")
    gateway = SpendGateway(vault=vault, ledger=ledger, idempotency_db_path=tmp_path / "idempotency.sqlite3")

    with patch(
        "ops.spend_gateway_v1.execute_once",
        return_value={"status": "IN_FLIGHT", "response": None},
    ):
        decision = gateway.request(_req(amount="100.00", request_id="req-in-flight"), idempotency_key="idem-in-flight")

    assert decision.allowed is False
    assert decision.reason == "IDEMPOTENCY_IN_FLIGHT"
    assert vault.calls == 0

    events = read_events(ledger.path)
    assert len(events) == 1
    assert events[0]["event_type"] == "SPEND_DENIED"
    assert events[0]["payload"]["reason"] == "IDEMPOTENCY_IN_FLIGHT"


def test_spend_gateway_unexpected_status_is_fail_closed_and_logs_denial(tmp_path: Path) -> None:
    vault = _Vault()
    ledger = SimpleNamespace(path=tmp_path / "events.ndjson")
    gateway = SpendGateway(vault=vault, ledger=ledger, idempotency_db_path=tmp_path / "idempotency.sqlite3")

    with patch(
        "ops.spend_gateway_v1.execute_once",
        return_value={"status": "BROKEN", "response": None},
    ):
        decision = gateway.request(_req(amount="100.00", request_id="req-broken"), idempotency_key="idem-broken")

    assert decision.allowed is False
    assert decision.reason == "IDEMPOTENCY_UNEXPECTED_STATUS"
    assert decision.meta["idempotency_status"] == "BROKEN"
    assert vault.calls == 0

    events = read_events(ledger.path)
    assert len(events) == 1
    assert events[0]["event_type"] == "SPEND_DENIED"
    assert events[0]["payload"]["reason"] == "IDEMPOTENCY_UNEXPECTED_STATUS"
    assert events[0]["payload"]["idempotency_status"] == "BROKEN"
