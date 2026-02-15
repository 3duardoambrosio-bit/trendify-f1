"""Meta Safe Client: PAUSED-by-default, spend caps, circuit breaker, ledger. S7."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from synapse.config.thresholds import (
    AUTOPAUSE_RATIO,
    DEFAULT_DAILY_SPEND_CAP_MXN,
    META_CB_FAILURES,
    META_CB_RESET_S,
    META_RETRIES,
    META_TIMEOUT_S,
)
from synapse.infra.circuit_breaker import CircuitBreaker, CircuitOpenError
from synapse.infra.feature_flags import FeatureFlags
from synapse.infra.idempotency_store import IdempotencyStore
from synapse.infra.ledger_f1_core import Ledger
from synapse.infra.retry_policy import RetryPolicy
from synapse.meta.publisher_adapter import call_create_campaign, call_pause_campaign


def _generate_mock_id(idempotency_key: str) -> str:
    h = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"MOCK_CAMP_{h}"


@dataclass
class MetaSafeClientConfig:
    daily_spend_cap_mxn: Decimal = DEFAULT_DAILY_SPEND_CAP_MXN
    autopause_ratio: Decimal = AUTOPAUSE_RATIO
    meta_timeout_s: int = META_TIMEOUT_S
    meta_retries: int = META_RETRIES
    meta_cb_failures: int = META_CB_FAILURES
    meta_cb_reset_s: int = META_CB_RESET_S


@dataclass
class MetaSafeClient:
    """Institutional safe wrapper over Meta campaign creation.

    - PAUSED by default (always forces status=PAUSED)
    - Spend cap with auto-pause at 80%
    - Circuit breaker + retry against graph.facebook.com
    - Feature flag meta_live_api (default OFF = mock)
    - Ledger logging for every attempt/result
    - Idempotency: deterministic key prevents duplicates
    """

    feature_flags: FeatureFlags
    retry_policy: RetryPolicy
    circuit_breaker: CircuitBreaker
    idempotency_store: IdempotencyStore
    ledger: Ledger
    config: MetaSafeClientConfig = field(default_factory=MetaSafeClientConfig)

    @property
    def _is_live(self) -> bool:
        return self.feature_flags.is_on("meta_live_api", default=False)

    # ------------------------------------------------------------------
    # create_campaign_safe
    # ------------------------------------------------------------------
    def create_campaign_safe(
        self,
        payload: Dict[str, Any],
        idempotency_key: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        # Force PAUSED regardless of what caller sends
        payload = dict(payload)
        payload["status"] = "PAUSED"

        # Idempotency check
        existing = self.idempotency_store.get(idempotency_key)
        if existing is not None:
            try:
                cached = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                cached = {"raw": existing}
            return {
                "ok": True,
                "mode": "cached",
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
                "result": cached,
            }

        # Ledger: attempt
        self.ledger.append(
            event_type="meta.create_campaign.attempt",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            severity="INFO",
            payload={"live": self._is_live, "campaign_payload": payload},
        )

        if not self._is_live:
            # Mock mode
            mock_id = _generate_mock_id(idempotency_key)
            result = {
                "ok": True,
                "mode": "mock",
                "campaign_id": mock_id,
                "status": "PAUSED",
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            }
            self.idempotency_store.put(
                idempotency_key, json.dumps(result, ensure_ascii=False),
            )
            self.ledger.append(
                event_type="meta.create_campaign.result",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                severity="INFO",
                payload=result,
            )
            return result

        # Live mode: retry + circuit breaker
        try:
            def _do_create() -> Dict[str, Any]:
                return self.circuit_breaker.call(
                    lambda: call_create_campaign(payload),
                )

            api_result = self.retry_policy.run(_do_create)

            result = {
                "ok": True,
                "mode": "live",
                "campaign_id": api_result.get("id"),
                "status": "PAUSED",
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
                "api_response": api_result,
            }
            self.idempotency_store.put(
                idempotency_key, json.dumps(result, ensure_ascii=False),
            )
            self.ledger.append(
                event_type="meta.create_campaign.result",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                severity="INFO",
                payload=result,
            )
            return result

        except CircuitOpenError as exc:
            return self._handle_error(
                exc, idempotency_key, correlation_id,
                error_code="circuit_open",
            )
        except Exception as exc:
            return self._handle_error(
                exc, idempotency_key, correlation_id,
                error_code="create_campaign_error",
            )

    # ------------------------------------------------------------------
    # maybe_autopause
    # ------------------------------------------------------------------
    def maybe_autopause(
        self,
        spend_today_mxn: Decimal,
        cap_mxn: Optional[Decimal] = None,
        campaign_id: str = "",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        if cap_mxn is None:
            cap_mxn = self.config.daily_spend_cap_mxn

        threshold = cap_mxn * self.config.autopause_ratio
        should_pause = spend_today_mxn >= threshold
        idem_key = f"autopause:{campaign_id}:{spend_today_mxn}"

        self.ledger.append(
            event_type="meta.autopause.attempt",
            correlation_id=correlation_id,
            idempotency_key=idem_key,
            severity="INFO",
            payload={
                "spend_today_mxn": str(spend_today_mxn),
                "cap_mxn": str(cap_mxn),
                "threshold_mxn": str(threshold),
                "should_pause": should_pause,
                "campaign_id": campaign_id,
                "live": self._is_live,
            },
        )

        if not should_pause:
            result: Dict[str, Any] = {
                "ok": True,
                "action": "NONE",
                "reason": "below_threshold",
                "spend_today_mxn": str(spend_today_mxn),
                "threshold_mxn": str(threshold),
                "campaign_id": campaign_id,
                "correlation_id": correlation_id,
            }
            self.ledger.append(
                event_type="meta.autopause.result",
                correlation_id=correlation_id,
                idempotency_key=idem_key,
                severity="INFO",
                payload=result,
            )
            return result

        # Should pause
        if not self._is_live:
            result = {
                "ok": True,
                "action": "PAUSE",
                "mode": "mock",
                "reason": "spend_at_or_above_threshold",
                "spend_today_mxn": str(spend_today_mxn),
                "threshold_mxn": str(threshold),
                "campaign_id": campaign_id,
                "correlation_id": correlation_id,
            }
            self.ledger.append(
                event_type="meta.autopause.result",
                correlation_id=correlation_id,
                idempotency_key=idem_key,
                severity="WARN",
                payload=result,
            )
            return result

        # Live pause
        try:
            def _do_pause() -> Dict[str, Any]:
                return self.circuit_breaker.call(
                    lambda: call_pause_campaign(campaign_id),
                )

            self.retry_policy.run(_do_pause)

            result = {
                "ok": True,
                "action": "PAUSE",
                "mode": "live",
                "reason": "spend_at_or_above_threshold",
                "spend_today_mxn": str(spend_today_mxn),
                "threshold_mxn": str(threshold),
                "campaign_id": campaign_id,
                "correlation_id": correlation_id,
            }
            self.ledger.append(
                event_type="meta.autopause.result",
                correlation_id=correlation_id,
                idempotency_key=idem_key,
                severity="WARN",
                payload=result,
            )
            return result

        except Exception as exc:
            return self._handle_error(
                exc, idem_key, correlation_id,
                error_code="autopause_error",
            )

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _handle_error(
        self,
        exc: Exception,
        idempotency_key: str,
        correlation_id: str,
        error_code: str = "unknown_error",
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": False,
            "error_code": error_code,
            "error_message": str(exc),
            "error_type": type(exc).__name__,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
        }
        self.ledger.append(
            event_type="meta.error",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            severity="ERROR",
            payload=result,
        )
        return result
