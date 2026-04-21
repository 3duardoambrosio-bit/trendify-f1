from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Protocol

from .autopilot_runtime_v1 import AutopilotRuntimeResult, PublisherAction


class SafeClientLike(Protocol):
    def create_campaign_safe(
        self,
        payload: Dict[str, Any],
        idempotency_key: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    def maybe_autopause(
        self,
        spend_today_mxn: Decimal,
        cap_mxn: Optional[Decimal] = None,
        campaign_id: str = "",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]: ...


@dataclass(frozen=True)
class OpsOrchestratorRequest:
    runtime_result: AutopilotRuntimeResult
    campaign_payload: Optional[Dict[str, Any]] = None
    campaign_id: str = ""
    spend_today_mxn: Optional[Decimal] = None
    cap_mxn: Optional[Decimal] = None
    idempotency_key: str = ""
    correlation_id: str = ""


@dataclass(frozen=True)
class OpsOrchestratorResult:
    ok: bool
    status: str
    publisher_action: Optional[PublisherAction]
    correlation_id: str
    error_code: Optional[str]
    publish_result: Optional[Dict[str, Any]]
    runtime_result: Dict[str, Any]


class OpsOrchestratorV1:
    def __init__(self, *, safe_client: SafeClientLike) -> None:
        self.safe_client = safe_client

    def dispatch(self, request: OpsOrchestratorRequest) -> OpsOrchestratorResult:
        runtime = request.runtime_result
        correlation_id = request.correlation_id or runtime.correlation_id

        if runtime.publisher_action is None:
            return OpsOrchestratorResult(
                ok=True,
                status="SKIPPED",
                publisher_action=None,
                correlation_id=correlation_id,
                error_code=None,
                publish_result=None,
                runtime_result=runtime.to_dict(),
            )

        if runtime.publisher_action == "create_campaign":
            if not request.campaign_payload:
                raise ValueError("campaign_payload_required_for_create_campaign")
            if not str(request.idempotency_key).strip():
                raise ValueError("idempotency_key_required_for_create_campaign")

            publish_result = self.safe_client.create_campaign_safe(
                payload=dict(request.campaign_payload),
                idempotency_key=request.idempotency_key,
                correlation_id=correlation_id,
            )
            ok = bool(publish_result.get("ok"))

            return OpsOrchestratorResult(
                ok=ok,
                status="DISPATCHED" if ok else "FAILED",
                publisher_action=runtime.publisher_action,
                correlation_id=correlation_id,
                error_code=None if ok else str(publish_result.get("error_code") or "create_campaign_failed"),
                publish_result=publish_result,
                runtime_result=runtime.to_dict(),
            )

        if runtime.publisher_action == "pause_campaign":
            if not str(request.campaign_id).strip():
                raise ValueError("campaign_id_required_for_pause_campaign")
            if request.spend_today_mxn is None:
                raise ValueError("spend_today_mxn_required_for_pause_campaign")
            if request.cap_mxn is None:
                raise ValueError("cap_mxn_required_for_pause_campaign")

            publish_result = self.safe_client.maybe_autopause(
                spend_today_mxn=Decimal(request.spend_today_mxn),
                cap_mxn=Decimal(request.cap_mxn),
                campaign_id=request.campaign_id,
                correlation_id=correlation_id,
            )
            executed = bool(publish_result.get("ok")) and publish_result.get("action") == "PAUSE"

            return OpsOrchestratorResult(
                ok=executed,
                status="DISPATCHED" if executed else "NOT_EXECUTED",
                publisher_action=runtime.publisher_action,
                correlation_id=correlation_id,
                error_code=None if executed else "pause_not_executed",
                publish_result=publish_result,
                runtime_result=runtime.to_dict(),
            )

        raise ValueError(f"unsupported_publisher_action:{runtime.publisher_action}")
