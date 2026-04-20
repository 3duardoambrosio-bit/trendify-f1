from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from ops.spend_gateway_v1 import SpendGateway
from synapse.safety.circuit import CircuitBreaker, CircuitConfig, CircuitState


class _AlwaysTimeoutVault:
    def __init__(self) -> None:
        self.calls = 0

    def request_spend(self, req):
        self.calls += 1
        raise TimeoutError("vault_timeout")


class _FailOnceThenApproveVault:
    def __init__(self) -> None:
        self.calls = 0

    def request_spend(self, req):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("vault_timeout")
        return SimpleNamespace(allowed=True, reason="APPROVED")


def _req(request_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        budget="operational",
        amount=Decimal("10.00"),
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


def test_spend_gateway_trips_safety_circuit_after_repeated_vault_errors(tmp_path) -> None:
    breaker = CircuitBreaker(
        CircuitConfig(
            failure_threshold=2,
            success_threshold=1,
            cooldown_seconds=3600,
            max_cooldown_seconds=3600,
        )
    )
    vault = _AlwaysTimeoutVault()
    gateway = SpendGateway(
        vault=vault,
        circuit_breaker=breaker,
        idempotency_db_path=tmp_path / "idem.sqlite3",
    )

    d1 = gateway.request(_req("r1"), idempotency_key="k1")
    assert d1.allowed is False
    assert d1.reason.startswith("VAULT_REQUEST_ERROR:TimeoutError:")
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failures == 1

    d2 = gateway.request(_req("r2"), idempotency_key="k2")
    assert d2.allowed is False
    assert d2.reason.startswith("VAULT_REQUEST_ERROR:TimeoutError:")
    assert breaker.state == CircuitState.OPEN
    assert breaker.failures == 2
    assert vault.calls == 2

    d3 = gateway.request(_req("r3"), idempotency_key="k3")
    assert d3.allowed is False
    assert "CIRCUIT_OPEN" in d3.reason
    assert breaker.state == CircuitState.OPEN
    assert vault.calls == 2


def test_spend_gateway_success_resets_safety_circuit_failures(tmp_path) -> None:
    breaker = CircuitBreaker(
        CircuitConfig(
            failure_threshold=3,
            success_threshold=1,
            cooldown_seconds=3600,
            max_cooldown_seconds=3600,
        )
    )
    vault = _FailOnceThenApproveVault()
    gateway = SpendGateway(
        vault=vault,
        circuit_breaker=breaker,
        idempotency_db_path=tmp_path / "idem.sqlite3",
    )

    d1 = gateway.request(_req("r1"), idempotency_key="k1")
    assert d1.allowed is False
    assert d1.reason.startswith("VAULT_REQUEST_ERROR:TimeoutError:")
    assert breaker.failures == 1
    assert breaker.state == CircuitState.CLOSED

    d2 = gateway.request(_req("r2"), idempotency_key="k2")
    assert d2.allowed is True
    assert d2.reason == "APPROVED"
    assert breaker.failures == 0
    assert breaker.state == CircuitState.CLOSED
    assert vault.calls == 2
