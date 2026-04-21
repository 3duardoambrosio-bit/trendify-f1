from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from synapse.infra.alerts import NullAlertSink


def test_safe_client_alerts_grep_present():
    import pathlib
    src = pathlib.Path("synapse/meta/safe_client.py").read_text(encoding="utf-8")
    assert "get_alert_sink" in src


def test_safe_client_alerts_on_spend_block(tmp_path):
    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
        with patch("synapse.meta.safe_client._check_capital_shield") as mock_cs:
            mock_cs.return_value = {"gate": "capital_shield", "allowed": False, "reason": "test_block"}
            with patch("synapse.meta.safe_client._check_safety_middleware") as mock_sm:
                mock_sm.return_value = {"gate": "safety_middleware", "allowed": True, "reason": "passed"}

                from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig
                from synapse.infra.circuit_breaker import CircuitBreaker
                from synapse.infra.feature_flags import FeatureFlags
                from synapse.infra.retry_policy import RetryPolicy

                client = MetaSafeClient(
                    feature_flags=FeatureFlags(values={}),
                    retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
                    circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
                    idempotency_store=SimpleNamespace(path=tmp_path / "idem.sqlite3"),
                    ledger=SimpleNamespace(path=tmp_path / "ledger.ndjson"),
                    config=MetaSafeClientConfig(),
                )

                result = client.create_campaign_safe(
                    payload={"budget_mxn": "100"},
                    idempotency_key="test-key-1",
                )

    assert result["ok"] is False
    assert "capital_shield" in result.get("blocked_by", [])
    assert len(calls) >= 1
    assert "SPEND BLOCKED" in calls[0]

def test_safe_client_alerts_include_gate_reason_and_correlation(tmp_path):
    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
        with patch("synapse.meta.safe_client._check_capital_shield") as mock_cs:
            mock_cs.return_value = {
                "gate": "capital_shield",
                "allowed": False,
                "reason": "test_block",
                "correlation_id": "corr-alert-1",
            }
            with patch("synapse.meta.safe_client._check_safety_middleware") as mock_sm:
                mock_sm.return_value = {
                    "gate": "safety_middleware",
                    "allowed": True,
                    "reason": "passed",
                    "correlation_id": "corr-alert-1",
                }

                from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig
                from synapse.infra.circuit_breaker import CircuitBreaker
                from synapse.infra.feature_flags import FeatureFlags
                from synapse.infra.retry_policy import RetryPolicy

                client = MetaSafeClient(
                    feature_flags=FeatureFlags(values={}),
                    retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
                    circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
                    idempotency_store=SimpleNamespace(path=tmp_path / "idem.sqlite3"),
                    ledger=SimpleNamespace(path=tmp_path / "ledger.ndjson"),
                    config=MetaSafeClientConfig(),
                )

                result = client.create_campaign_safe(
                    payload={"budget_mxn": "100"},
                    idempotency_key="test-key-alert-fidelity",
                    correlation_id="corr-alert-1",
                )

    assert result["ok"] is False
    assert "capital_shield" in result.get("blocked_by", [])
    assert len(calls) >= 1
    assert "SPEND BLOCKED" in calls[0]
    assert "capital_shield:test_block" in calls[0]
    assert "corr=corr-alert-1" in calls[0]

