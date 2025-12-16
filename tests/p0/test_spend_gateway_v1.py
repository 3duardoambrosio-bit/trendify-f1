import json
from decimal import Decimal
from infra.ledger_ndjson import LedgerNDJSON
from vault.vault_p0 import VaultP0
from vault.cashflow_v1 import CashflowState
from ops.spend_gateway_v1 import SpendGatewayV1


def read_events(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def test_spend_denied_by_cashflow(tmp_path):
    ledger_path = tmp_path / "events.ndjson"
    ledger = LedgerNDJSON(ledger_path)
    vault = VaultP0(total_budget=Decimal("100.00"))
    cash = CashflowState(available_cash=Decimal("10.00"), projected_refunds=Decimal("0"))
    gw = SpendGatewayV1(ledger=ledger, vault=vault, cashflow=cash, safety_buffer=Decimal("5.00"))

    r = gw.request_spend(product_id="r004", pool="learning", amount=Decimal("6.00"))
    assert r.allowed is False
    assert r.reason == "cashflow_buffer"

    ev = read_events(ledger_path)
    assert ev[0]["event_type"] == "SPEND_REQUESTED"
    assert ev[1]["event_type"] == "SPEND_DENIED"


def test_spend_denied_by_reserve(tmp_path):
    ledger_path = tmp_path / "events.ndjson"
    ledger = LedgerNDJSON(ledger_path)
    vault = VaultP0(total_budget=Decimal("100.00"))
    cash = CashflowState(available_cash=Decimal("100.00"))
    gw = SpendGatewayV1(ledger=ledger, vault=vault, cashflow=cash, safety_buffer=Decimal("0.00"))

    r = gw.request_spend(product_id="r004", pool="reserve", amount=Decimal("1.00"))
    assert r.allowed is False
    assert r.reason == "reserve_protected"


def test_spend_approved_logs(tmp_path):
    ledger_path = tmp_path / "events.ndjson"
    ledger = LedgerNDJSON(ledger_path)
    vault = VaultP0(total_budget=Decimal("100.00"))
    cash = CashflowState(available_cash=Decimal("100.00"))
    gw = SpendGatewayV1(ledger=ledger, vault=vault, cashflow=cash, safety_buffer=Decimal("0.00"))

    r = gw.request_spend(product_id="r004", pool="learning", amount=Decimal("1.00"))
    assert r.allowed is True

    ev = read_events(ledger_path)
    assert ev[-1]["event_type"] == "SPEND_APPROVED"