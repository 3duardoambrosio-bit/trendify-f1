from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch

from config.feature_flags import FeatureFlags
from ops.autopilot_runtime_v1 import AutopilotRuntimeResult
from ops.ops_orchestrator_v1 import OpsOrchestratorRequest, OpsOrchestratorV1
from synapse.integrations.http_client import HttpRequest, SimpleHttpClient


class ExplodingSafeClient:
    def create_campaign_safe(self, *args, **kwargs):
        raise AssertionError("create_campaign_safe_must_not_be_called_in_no_publish_readiness")

    def maybe_autopause(self, *args, **kwargs):
        raise AssertionError("maybe_autopause_must_not_be_called_in_no_publish_readiness")


class RecordingSafeClient:
    def __init__(self) -> None:
        self.create_calls = []
        self.pause_calls = []

    def create_campaign_safe(self, payload, idempotency_key, correlation_id=None):
        self.create_calls.append(
            {
                "payload": dict(payload),
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            }
        )
        return {
            "ok": True,
            "mode": "mock",
            "action": "CREATE",
            "campaign_id": "mock-campaign-readiness",
            "correlation_id": correlation_id,
        }

    def maybe_autopause(
        self,
        spend_today_mxn: Decimal,
        cap_mxn: Decimal | None = None,
        campaign_id: str = "",
        correlation_id: str | None = None,
    ):
        self.pause_calls.append(
            {
                "spend_today_mxn": str(spend_today_mxn),
                "cap_mxn": str(cap_mxn),
                "campaign_id": campaign_id,
                "correlation_id": correlation_id,
            }
        )
        return {
            "ok": True,
            "mode": "mock",
            "action": "PAUSE",
            "campaign_id": campaign_id,
            "correlation_id": correlation_id,
        }


def _runtime(
    *,
    publisher_action,
    correlation_id: str = "corr-readiness",
) -> AutopilotRuntimeResult:
    return AutopilotRuntimeResult(
        product_id="p-readiness",
        correlation_id=correlation_id,
        action="hold" if publisher_action is None else "publish",
        allocated_budget=Decimal("0"),
        reason="readiness_contract",
        final_decision="approved",
        current_roas=1.0,
        spend=Decimal("0"),
        requested_budget=Decimal("0"),
        capital_reason=None,
        kill_action=None,
        publisher_action=publisher_action,
    )


def test_feature_flags_default_to_no_network_and_no_spend() -> None:
    flags = FeatureFlags(values={})

    assert flags.dry_run is True
    assert flags.meta_live is False
    assert flags.shopify_live is False
    assert flags.dropi_live is False
    assert flags.spend_real_money is False

    assert flags.allow_network("meta") is False
    assert flags.allow_network("shopify") is False
    assert flags.allow_network("dropi") is False
    assert flags.allow_network("unknown") is False

    exported = flags.as_dict()
    assert exported["dry_run"] is True
    assert exported["live_meta"] is False
    assert exported["live_shopify"] is False
    assert exported["live_dropi"] is False
    assert exported["spend_real_money"] is False


def test_feature_flags_dry_run_blocks_network_even_when_live_flags_are_true() -> None:
    flags = FeatureFlags(
        values={
            "dry_run": True,
            "meta_live_api": True,
            "shopify_live_api": True,
            "dropi_live_api": True,
            "spend_real_money": True,
        }
    )

    assert flags.dry_run is True
    assert flags.meta_live is True
    assert flags.shopify_live is True
    assert flags.dropi_live is True
    assert flags.spend_real_money is True

    assert flags.allow_network("meta") is False
    assert flags.allow_network("shopify") is False
    assert flags.allow_network("dropi") is False


def test_simple_http_client_dry_run_returns_synthetic_response_without_urlopen() -> None:
    client = SimpleHttpClient(dry_run=True)

    with patch("urllib.request.urlopen") as urlopen:
        response = client.request(
            HttpRequest(
                method="POST",
                url="https://example.test/no-live-readiness",
                headers={"Authorization": "Bearer SHOULD_NOT_LEAVE_PROCESS"},
                body=b'{"dry_run":true}',
                timeout_s=0.1,
            )
        )

    assert response.status == 200
    assert response.headers["x-dry-run"] == "1"
    assert json.loads(response.body.decode("utf-8")) == {
        "dry_run": True,
        "method": "POST",
        "url": "https://example.test/no-live-readiness",
    }
    urlopen.assert_not_called()


def test_orchestrator_no_publisher_action_skips_without_touching_safe_client() -> None:
    orchestrator = OpsOrchestratorV1(safe_client=ExplodingSafeClient())

    result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=_runtime(publisher_action=None),
            campaign_payload={"name": "must-not-publish"},
            campaign_id="must-not-pause",
            spend_today_mxn=Decimal("999"),
            cap_mxn=Decimal("1"),
            idempotency_key="must-not-use",
            correlation_id="corr-no-publish",
        )
    )

    assert result.ok is True
    assert result.status == "SKIPPED"
    assert result.publisher_action is None
    assert result.error_code is None
    assert result.publish_result is None
    assert result.correlation_id == "corr-no-publish"


def test_orchestrator_create_campaign_readiness_uses_mock_safe_client_only() -> None:
    safe_client = RecordingSafeClient()
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)

    result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=_runtime(
                publisher_action="create_campaign",
                correlation_id="corr-create-readiness",
            ),
            campaign_payload={
                "name": "No Live Readiness",
                "status": "PAUSED",
                "budget_mxn": "0",
            },
            idempotency_key="readiness-create-001",
        )
    )

    assert result.ok is True
    assert result.status == "DISPATCHED"
    assert result.error_code is None
    assert result.publish_result is not None
    assert result.publish_result["mode"] == "mock"
    assert result.publish_result["action"] == "CREATE"
    assert result.publish_result["correlation_id"] == "corr-create-readiness"

    assert len(safe_client.create_calls) == 1
    assert safe_client.create_calls[0]["payload"]["status"] == "PAUSED"
    assert safe_client.create_calls[0]["payload"]["budget_mxn"] == "0"
    assert safe_client.pause_calls == []


def test_orchestrator_pause_readiness_uses_mock_safe_client_only() -> None:
    safe_client = RecordingSafeClient()
    orchestrator = OpsOrchestratorV1(safe_client=safe_client)

    result = orchestrator.dispatch(
        OpsOrchestratorRequest(
            runtime_result=_runtime(
                publisher_action="pause_campaign",
                correlation_id="corr-pause-readiness",
            ),
            campaign_id="camp-readiness",
            spend_today_mxn=Decimal("100"),
            cap_mxn=Decimal("100"),
        )
    )

    assert result.ok is True
    assert result.status == "DISPATCHED"
    assert result.error_code is None
    assert result.publish_result is not None
    assert result.publish_result["mode"] == "mock"
    assert result.publish_result["action"] == "PAUSE"
    assert result.publish_result["campaign_id"] == "camp-readiness"
    assert result.publish_result["correlation_id"] == "corr-pause-readiness"

    assert safe_client.create_calls == []
    assert len(safe_client.pause_calls) == 1
    assert safe_client.pause_calls[0]["campaign_id"] == "camp-readiness"
    assert safe_client.pause_calls[0]["spend_today_mxn"] == "100"
    assert safe_client.pause_calls[0]["cap_mxn"] == "100"
def test_feature_flags_dry_run_false_with_live_false_blocks_network() -> None:
    flags = FeatureFlags(
        values={
            "dry_run": False,
            "meta_live_api": False,
            "shopify_live_api": False,
            "dropi_live_api": False,
        }
    )

    assert flags.dry_run is False
    assert flags.meta_live is False
    assert flags.shopify_live is False
    assert flags.dropi_live is False

    assert flags.allow_network("meta") is False
    assert flags.allow_network("shopify") is False
    assert flags.allow_network("dropi") is False
    assert flags.allow_network("unknown") is False


def test_simple_http_client_dry_run_does_not_leak_authorization_header(capsys) -> None:
    secret = "SHOULD_NOT_LEAVE_PROCESS"
    client = SimpleHttpClient(dry_run=True)

    with patch("urllib.request.urlopen") as urlopen:
        response = client.request(
            HttpRequest(
                method="POST",
                url="https://example.test/no-live-readiness",
                headers={
                    "Authorization": f"Bearer {secret}",
                    "X-Api-Key": secret,
                },
                body=b'{"dry_run":true}',
                timeout_s=0.1,
            )
        )

    captured = capsys.readouterr()
    body_text = response.body.decode("utf-8", errors="replace")
    header_text = json.dumps(response.headers, sort_keys=True)

    assert response.status == 200
    assert response.headers["x-dry-run"] == "1"
    assert secret not in body_text
    assert secret not in header_text
    assert secret not in captured.out
    assert secret not in captured.err
    urlopen.assert_not_called()


def test_feature_flags_keep_network_and_spend_gates_independent() -> None:
    flags = FeatureFlags(
        values={
            "dry_run": False,
            "meta_live_api": True,
            "shopify_live_api": False,
            "dropi_live_api": False,
            "spend_real_money": False,
        }
    )

    assert flags.dry_run is False
    assert flags.meta_live is True
    assert flags.shopify_live is False
    assert flags.dropi_live is False
    assert flags.spend_real_money is False

    assert flags.allow_network("meta") is True
    assert flags.allow_network("shopify") is False
    assert flags.allow_network("dropi") is False
    assert flags.as_dict()["spend_real_money"] is False
