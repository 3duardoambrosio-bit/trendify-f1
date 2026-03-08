"""S20 P0 Tests: ops_tick inventory pre-flight gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.infra.alert_wiring import reset_alert_sink


@pytest.fixture(autouse=True)
def _clean_env():
    reset_alert_sink()
    old_catalog = os.environ.pop("SYNAPSE_INVENTORY_CATALOG", None)
    old_orders = os.environ.pop("SYNAPSE_RECONCILE_ORDERS", None)
    old_ledger = os.environ.pop("SYNAPSE_RECONCILE_LEDGER", None)
    old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    old_chat = os.environ.pop("TELEGRAM_CHAT_ID", None)
    yield
    reset_alert_sink()
    for k, v in [
        ("SYNAPSE_INVENTORY_CATALOG", old_catalog),
        ("SYNAPSE_RECONCILE_ORDERS", old_orders),
        ("SYNAPSE_RECONCILE_LEDGER", old_ledger),
        ("TELEGRAM_BOT_TOKEN", old_token),
        ("TELEGRAM_CHAT_ID", old_chat),
    ]:
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def _write_catalog_ndjson(tmp_path: Path, product_id: str, stock: int) -> Path:
    p = tmp_path / "catalog.ndjson"
    rows = [
        {"source_product_id": product_id, "title": "Test Product", "stock": stock},
    ]
    p.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    return p


def test_inventory_skipped_when_env_var_not_set_in_readonly():
    from synapse.ops_tick import _inventory_preflight

    result = _inventory_preflight(product_id="34357", effective_readonly=True)

    assert result["blocked"] is False
    assert result["status"] == "skipped"
    assert result["reason"] == "env_var_not_set"


def test_inventory_blocks_when_env_var_not_set_in_write_mode():
    from synapse.ops_tick import _inventory_preflight

    result = _inventory_preflight(product_id="34357", effective_readonly=False)

    assert result["blocked"] is True
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "env_var_not_set"


def test_inventory_passes_when_stock_positive(tmp_path: Path):
    from synapse.ops_tick import _inventory_preflight

    catalog = _write_catalog_ndjson(tmp_path, product_id="34357", stock=7)
    os.environ["SYNAPSE_INVENTORY_CATALOG"] = str(catalog)

    result = _inventory_preflight(product_id="34357", effective_readonly=False)

    assert result["blocked"] is False
    assert result["status"] == "PASS"
    assert result["reason"] == "stock_available"
    assert result["stock"] == 7


def test_inventory_blocks_when_stock_zero(tmp_path: Path):
    from synapse.ops_tick import _inventory_preflight

    catalog = _write_catalog_ndjson(tmp_path, product_id="34357", stock=0)
    os.environ["SYNAPSE_INVENTORY_CATALOG"] = str(catalog)

    result = _inventory_preflight(product_id="34357", effective_readonly=False)

    assert result["blocked"] is True
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "out_of_stock"


def test_inventory_block_emits_alert(tmp_path: Path):
    from synapse.infra.alerts import NullAlertSink
    from synapse.ops_tick import _inventory_preflight

    catalog = _write_catalog_ndjson(tmp_path, product_id="34357", stock=0)
    os.environ["SYNAPSE_INVENTORY_CATALOG"] = str(catalog)

    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
        result = _inventory_preflight(product_id="34357", effective_readonly=False)

    assert result["blocked"] is True
    assert len(calls) >= 1
    assert "INVENTORY BLOCKED" in calls[0]