"""Dropi order forwarding client with idempotency, retry, circuit breaker, ledger. S8."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from synapse.config.thresholds import (
    DROPI_CB_FAILURES,
    DROPI_CB_RESET_S,
    DROPI_RETRIES,
    DROPI_RETRY_BASE_DELAY_S,
    DROPI_RETRY_MAX_DELAY_S,
)
from synapse.infra.circuit_breaker import CircuitBreaker, CircuitOpenError
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.idempotency_store import IdempotencyStore
from synapse.infra.ledger_f1_core import Ledger
from synapse.infra.retry_policy import RetryPolicy


# ---------------------------------------------------------------------------
# Live adapter stubs (only called when dropi_live_orders=ON)
# ---------------------------------------------------------------------------

def _live_check_stock(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check stock via the real Dropi API. Live-only path."""
    raise NotImplementedError(
        "dropi_live_orders_not_implemented: live stock check requires "
        "DROPI_INTEGRATION_KEY and a running Dropi API endpoint."
    )


def _live_forward_order(order_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Forward order via the real Dropi API. Live-only path."""
    raise NotImplementedError(
        "dropi_live_orders_not_implemented: live order forwarding requires "
        "DROPI_INTEGRATION_KEY and a running Dropi API endpoint."
    )


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_order_id(idempotency_key: str) -> str:
    h = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"MOCK_DROPI_{h}"


def _mock_check_stock(items: List[Dict[str, Any]]) -> bool:
    """Mock stock: available if every item has quantity > 0."""
    for item in items:
        qty = item.get("quantity", 0)
        try:
            if int(qty) <= 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class DropiForwardConfig:
    retries: int = DROPI_RETRIES
    retry_base_delay_s: float = DROPI_RETRY_BASE_DELAY_S
    retry_max_delay_s: float = DROPI_RETRY_MAX_DELAY_S
    cb_failures: int = DROPI_CB_FAILURES
    cb_reset_s: float = DROPI_CB_RESET_S


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

@dataclass
class DropiForwardClient:
    """Institutional safe client for forwarding Shopify orders to Dropi.

    - Feature flag dropi_live_orders (default OFF = mock)
    - Idempotency per order
    - Retry with exponential backoff
    - Circuit breaker
    - Ledger NDJSON logging
    - Stock check before forward
    """

    feature_flags: FeatureFlags
    retry_policy: RetryPolicy
    circuit_breaker: CircuitBreaker
    idempotency_store: IdempotencyStore
    ledger: Ledger
    config: DropiForwardConfig = field(default_factory=DropiForwardConfig)

    # Hooks for testing: override the internal call fn for retry testing
    _forward_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = field(
        default=None, repr=False,
    )
    _stock_fn: Optional[Callable[[List[Dict[str, Any]]], bool]] = field(
        default=None, repr=False,
    )

    @property
    def _is_live(self) -> bool:
        return self.feature_flags.is_on("dropi_live_orders", default=False)

    # ------------------------------------------------------------------
    # forward_order
    # ------------------------------------------------------------------
    def forward_order(
        self,
        shopify_order: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        order_id = shopify_order.get("id") or shopify_order.get("order_number") or ""
        idempotency_key = f"dropi.forward:{order_id}"
        if correlation_id is None:
            correlation_id = f"dropi_forward:{order_id}"

        t0 = time.monotonic()

        # ── Idempotency check ──
        existing = self.idempotency_store.get(idempotency_key)
        if existing is not None:
            try:
                cached = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                cached = {"raw": existing}
            cached["idempotency_key"] = idempotency_key
            cached["correlation_id"] = correlation_id
            return cached

        # ── Stock check ──
        items: List[Dict[str, Any]] = shopify_order.get("line_items", [])

        self.ledger.append(
            event_type="dropi.stockcheck.attempt",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            severity="INFO",
            payload={"order_id": str(order_id), "item_count": len(items), "live": self._is_live},
        )

        stock_ok = self._check_stock(items)

        self.ledger.append(
            event_type="dropi.stockcheck.result",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            severity="INFO",
            payload={"stock_available": stock_ok, "order_id": str(order_id)},
        )

        if not stock_ok:
            result: Dict[str, Any] = {
                "ok": False,
                "mode": "mock" if not self._is_live else "live",
                "idempotency_key": idempotency_key,
                "order_id": str(order_id),
                "forwarded": False,
                "stock_available": False,
                "correlation_id": correlation_id,
                "timings": {"total_ms": int((time.monotonic() - t0) * 1000)},
            }
            self.idempotency_store.put(idempotency_key, json.dumps(result, ensure_ascii=False))
            return result

        # ── Forward attempt ──
        self.ledger.append(
            event_type="dropi.forward.attempt",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            severity="INFO",
            payload={"order_id": str(order_id), "live": self._is_live},
        )

        try:
            api_result = self._do_forward(shopify_order)
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            result = {
                "ok": True,
                "mode": "mock" if not self._is_live else "live",
                "idempotency_key": idempotency_key,
                "order_id": str(order_id),
                "forwarded": True,
                "stock_available": True,
                "correlation_id": correlation_id,
                "dropi_response": api_result,
                "timings": {"total_ms": elapsed_ms},
            }
            self.idempotency_store.put(idempotency_key, json.dumps(result, ensure_ascii=False))

            self.ledger.append(
                event_type="dropi.forward.result",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                severity="INFO",
                payload=result,
            )
            return result

        except CircuitOpenError as exc:
            return self._handle_error(exc, idempotency_key, correlation_id, order_id, t0, "circuit_open")

        except Exception as exc:
            return self._handle_error(exc, idempotency_key, correlation_id, order_id, t0, "forward_error")

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _check_stock(self, items: List[Dict[str, Any]]) -> bool:
        if self._stock_fn is not None:
            return self._stock_fn(items)
        if self._is_live:
            resp = _live_check_stock(items)
            return bool(resp.get("available", False))
        return _mock_check_stock(items)

    def _do_forward(self, order: Dict[str, Any]) -> Dict[str, Any]:
        fn = self._forward_fn if self._forward_fn is not None else self._default_forward_fn

        def _with_cb() -> Dict[str, Any]:
            return self.circuit_breaker.call(lambda: fn(order))

        return self.retry_policy.run(_with_cb)

    def _default_forward_fn(self, order: Dict[str, Any]) -> Dict[str, Any]:
        if self._is_live:
            return _live_forward_order(order)
        # Mock
        order_id = order.get("id") or order.get("order_number") or ""
        idem_key = f"dropi.forward:{order_id}"
        return {
            "dropi_order_id": _mock_order_id(idem_key),
            "status": "received",
            "mock": True,
        }

    def _handle_error(
        self,
        exc: Exception,
        idempotency_key: str,
        correlation_id: str,
        order_id: Any,
        t0: float,
        error_type: str,
    ) -> Dict[str, Any]:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result: Dict[str, Any] = {
            "ok": False,
            "mode": "mock" if not self._is_live else "live",
            "idempotency_key": idempotency_key,
            "order_id": str(order_id),
            "forwarded": False,
            "stock_available": True,
            "error": {"type": error_type, "msg": str(exc)},
            "correlation_id": correlation_id,
            "timings": {"total_ms": elapsed_ms},
        }
        self.ledger.append(
            event_type="dropi.forward.error",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            severity="ERROR",
            payload=result,
        )
        return result
