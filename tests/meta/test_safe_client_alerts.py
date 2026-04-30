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

def test_safe_client_error_alerts_include_code_type_corr_and_idem(tmp_path):
    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
        with patch(
            "synapse.meta.safe_client.call_pause_campaign",
            side_effect=RuntimeError("pause_boom"),
        ):
            from synapse.meta.safe_client import MetaSafeClient, MetaSafeClientConfig
            from synapse.infra.circuit_breaker import CircuitBreaker
            from synapse.infra.feature_flags import FeatureFlags
            from synapse.infra.retry_policy import RetryPolicy

            client = MetaSafeClient(
                feature_flags=FeatureFlags(values={"meta_live_api": True}),
                retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
                circuit_breaker=CircuitBreaker(failure_threshold=5, reset_timeout_s=30.0),
                idempotency_store=SimpleNamespace(path=tmp_path / "idem.sqlite3"),
                ledger=SimpleNamespace(path=tmp_path / "ledger.ndjson"),
                config=MetaSafeClientConfig(),
            )

            result = client.maybe_autopause(
                spend_today_mxn=100,
                cap_mxn=100,
                campaign_id="camp-alert-err",
                correlation_id="corr-alert-err",
            )

    assert result["ok"] is False
    assert result["error_code"] == "autopause_error"
    assert len(calls) >= 1
    assert "META ERROR:" in calls[0]
    assert "code=autopause_error" in calls[0]
    assert "type=RuntimeError" in calls[0]
    assert "corr=corr-alert-err" in calls[0]
    assert "idem=autopause:camp-alert-err:100" in calls[0]

def test_safe_client_alerts_on_autopause_action(tmp_path):
    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
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

        result = client.maybe_autopause(
            spend_today_mxn=100,
            cap_mxn=100,
            campaign_id="camp-alert-pause",
            correlation_id="corr-ap-alert",
        )

    assert result["ok"] is True
    assert result["action"] == "PAUSE"
    assert len(calls) >= 1
    assert "AUTOPAUSE" in calls[0]
    assert "action=PAUSE" in calls[0]
    assert "mode=mock" in calls[0]
    assert "reason=spend_at_or_above_threshold" in calls[0]
    assert "campaign_id=camp-alert-pause" in calls[0]
    assert "corr=corr-ap-alert" in calls[0]

def test_safe_client_alerts_on_create_campaign_action(tmp_path):
    mock_sink = NullAlertSink()
    calls = []
    original_send = mock_sink.send

    def tracking_send(text, **kwargs):
        calls.append(text)
        return original_send(text, **kwargs)

    mock_sink.send = tracking_send

    with patch("synapse.infra.alert_wiring.get_alert_sink", return_value=mock_sink):
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
            payload={"name": "Camp Alert", "budget_mxn": "100"},
            idempotency_key="idem-create-alert",
            correlation_id="corr-create-alert",
        )

    assert result["ok"] is True
    assert result["mode"] == "mock"
    assert result["status"] == "PAUSED"
    assert len(calls) >= 1
    assert "CREATE_CAMPAIGN" in calls[0]
    assert "mode=mock" in calls[0]
    assert "status=PAUSED" in calls[0]
    assert "campaign_id=" in calls[0]
    assert "corr=corr-create-alert" in calls[0]

