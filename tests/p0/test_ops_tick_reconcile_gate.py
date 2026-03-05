"""S19 P0 Tests: ops_tick reconcile pre-flight gate."""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.infra.alert_wiring import reset_alert_sink


@pytest.fixture(autouse=True)
def _clean_env():
    reset_alert_sink()
    old_orders = os.environ.pop("SYNAPSE_RECONCILE_ORDERS", None)
    old_ledger = os.environ.pop("SYNAPSE_RECONCILE_LEDGER", None)
    old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    old_chat = os.environ.pop("TELEGRAM_CHAT_ID", None)
    yield
    reset_alert_sink()
    for k, v in [
        ("SYNAPSE_RECONCILE_ORDERS", old_orders),
        ("SYNAPSE_RECONCILE_LEDGER", old_ledger),
        ("TELEGRAM_BOT_TOKEN", old_token),
        ("TELEGRAM_CHAT_ID", old_chat),
    ]:
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def test_reconcile_skipped_when_env_vars_not_set():
    """Without env vars, reconcile gate is skipped (not blocked)."""
    from synapse.ops_tick import _reconcile_preflight
    result = _reconcile_preflight()
    assert result["blocked"] is False
    assert result["status"] == "skipped"


def test_reconcile_passes_when_data_matches(tmp_path):
    """Matching orders + ledger → gate passes."""
    orders = tmp_path / "orders.json"
    ledger = tmp_path / "ledger.ndjson"

    orders.write_text(json.dumps([
        {"id": 1, "financial_status": "paid", "total_price": "100.00", "currency": "MXN"}
    ]), encoding="utf-8")
    ledger.write_text('{"order_id":"1","amount_mxn":"100.00"}\n', encoding="utf-8")

    os.environ["SYNAPSE_RECONCILE_ORDERS"] = str(orders)
    os.environ["SYNAPSE_RECONCILE_LEDGER"] = str(ledger)

    from synapse.ops_tick import _reconcile_preflight
    result = _reconcile_preflight()
    assert result["blocked"] is False
    assert result["status"] == "PASS"


def test_reconcile_blocks_when_order_missing_from_ledger(tmp_path):
    """Paid order not in ledger → gate BLOCKS."""
    orders = tmp_path / "orders.json"
    ledger = tmp_path / "ledger.ndjson"

    orders.write_text(json.dumps([
        {"id": 1, "financial_status": "paid", "total_price": "100.00", "currency": "MXN"}
    ]), encoding="utf-8")
    ledger.write_text("", encoding="utf-8")  # empty ledger

    os.environ["SYNAPSE_RECONCILE_ORDERS"] = str(orders)
    os.environ["SYNAPSE_RECONCILE_LEDGER"] = str(ledger)

    from synapse.ops_tick import _reconcile_preflight
    result = _reconcile_preflight()
    assert result["blocked"] is True
    assert result["status"] == "BLOCKED"


def test_reconcile_block_emits_alert(tmp_path):
    """When reconcile blocks, an alert should be attempted."""
    orders = tmp_path / "orders.json"
    ledger = tmp_path / "ledger.ndjson"

    orders.write_text(json.dumps([
        {"id": 1, "financial_status": "paid", "total_price": "100.00"}
    ]), encoding="utf-8")
    ledger.write_text("", encoding="utf-8")

    os.environ["SYNAPSE_RECONCILE_ORDERS"] = str(orders)
    os.environ["SYNAPSE_RECONCILE_LEDGER"] = str(ledger)

    # Track alert calls via NullAlertSink (no real Telegram)
    from synapse.infra.alerts import NullAlertSink
    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
        from synapse.ops_tick import _reconcile_preflight
        result = _reconcile_preflight()

    assert result["blocked"] is True
    assert len(calls) >= 1
    assert "RECONCILE BLOCKED" in calls[0]
