"""Tests for Dropi order forwarding client. S8."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from synapse.infra.circuit_breaker import CircuitBreaker, CircuitOpenError
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.idempotency_store import IdempotencyStore
from synapse.infra.ledger_f1_core import Ledger
from synapse.infra.retry_policy import RetryPolicy
from synapse.dropi.forward_client import DropiForwardClient, DropiForwardConfig


def _make_client(
    tmp_path: Path,
    *,
    live: bool = False,
    forward_fn: Any = None,
    stock_fn: Any = None,
    retries: int = 3,
    cb_failures: int = 5,
) -> DropiForwardClient:
    flags = FeatureFlags(values={"dropi_live_orders": True} if live else {})
    return DropiForwardClient(
        feature_flags=flags,
        retry_policy=RetryPolicy(max_attempts=retries, base_delay_s=0.0, max_delay_s=0.0),
        circuit_breaker=CircuitBreaker(failure_threshold=cb_failures, reset_timeout_s=30.0),
        idempotency_store=IdempotencyStore.open(tmp_path / "idem.json"),
        ledger=Ledger.open(tmp_path / "ledger.ndjson"),
        config=DropiForwardConfig(),
        _forward_fn=forward_fn,
        _stock_fn=stock_fn,
    )


def _read_ledger(tmp_path: Path) -> List[Dict[str, Any]]:
    p = tmp_path / "ledger.ndjson"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text("utf-8").splitlines() if ln.strip()]


def _sample_order(order_id: int = 1001, qty: int = 2) -> Dict[str, Any]:
    return {
        "id": order_id,
        "order_number": f"#{order_id}",
        "line_items": [
            {"variant_id": 5001, "quantity": qty, "title": "Test Product"},
        ],
    }


# ------------------------------------------------------------------
# 1) Mock success + ledger
# ------------------------------------------------------------------
class TestForwardMockSuccess:
    def test_mock_returns_ok_forwarded(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        result = client.forward_order(_sample_order())
        assert result["ok"] is True
        assert result["forwarded"] is True
        assert result["mode"] == "mock"
        assert result["stock_available"] is True
        assert result["order_id"] == "1001"

    def test_ledger_contains_forward_result(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        client.forward_order(_sample_order())
        events = _read_ledger(tmp_path)
        types = [e["event_type"] for e in events]
        assert "dropi.forward.attempt" in types
        assert "dropi.forward.result" in types
        assert "dropi.stockcheck.attempt" in types
        assert "dropi.stockcheck.result" in types


# ------------------------------------------------------------------
# 2) Idempotency — second call short-circuits
# ------------------------------------------------------------------
class TestIdempotency:
    def test_second_call_returns_cached(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        r1 = client.forward_order(_sample_order(1001))
        r2 = client.forward_order(_sample_order(1001))

        assert r1["forwarded"] is True
        assert r2["forwarded"] is True
        assert r1["idempotency_key"] == r2["idempotency_key"]

        # Only one forward.attempt in ledger
        events = _read_ledger(tmp_path)
        attempt_count = sum(1 for e in events if e["event_type"] == "dropi.forward.attempt")
        assert attempt_count == 1


# ------------------------------------------------------------------
# 3) Stock unavailable blocks forward
# ------------------------------------------------------------------
class TestStockUnavailable:
    def test_zero_quantity_blocks(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        order = _sample_order(qty=0)
        result = client.forward_order(order)
        assert result["ok"] is False
        assert result["forwarded"] is False
        assert result["stock_available"] is False

    def test_custom_stock_fn_blocks(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path, stock_fn=lambda items: False)
        result = client.forward_order(_sample_order())
        assert result["ok"] is False
        assert result["forwarded"] is False
        assert result["stock_available"] is False


# ------------------------------------------------------------------
# 4) Retry then success
# ------------------------------------------------------------------
class TestRetryThenSuccess:
    def test_fails_twice_then_succeeds(self, tmp_path: Path) -> None:
        call_count = 0

        def flaky_forward(order: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary failure")
            return {"dropi_order_id": "DRP-999", "status": "received", "mock": True}

        client = _make_client(tmp_path, forward_fn=flaky_forward, retries=3)
        result = client.forward_order(_sample_order(2001))
        assert result["ok"] is True
        assert result["forwarded"] is True
        assert call_count == 3


# ------------------------------------------------------------------
# 5) Circuit breaker opens after threshold
# ------------------------------------------------------------------
class TestCircuitBreaker:
    def test_opens_after_repeated_failures(self, tmp_path: Path) -> None:
        call_count = 0

        def always_fail(order: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        # cb_failures=2, retries=1 so each order attempt trips CB fast
        client = _make_client(tmp_path, forward_fn=always_fail, retries=1, cb_failures=2)

        # First call: fails (cb records 1 failure)
        r1 = client.forward_order(_sample_order(3001))
        assert r1["ok"] is False

        # Second call with different order: fails (cb records 2nd failure, opens)
        r2 = client.forward_order(_sample_order(3002))
        assert r2["ok"] is False

        # Third call: circuit should be open
        r3 = client.forward_order(_sample_order(3003))
        assert r3["ok"] is False
        assert r3["error"]["type"] == "circuit_open"


# ------------------------------------------------------------------
# 6) Live flag calls live path => NotImplementedError
# ------------------------------------------------------------------
class TestLiveFlag:
    def test_live_raises_not_implemented(self, tmp_path: Path) -> None:
        # Provide stock_fn=True so we bypass live stock check and reach forward
        client = _make_client(tmp_path, live=True, stock_fn=lambda items: True)
        result = client.forward_order(_sample_order(4001))
        # The live forward path raises NotImplementedError which is caught
        assert result["ok"] is False
        assert "error" in result
        assert "not_implemented" in result["error"]["msg"].lower() or \
               "forward_error" == result["error"]["type"]
