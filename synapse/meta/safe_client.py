"""Meta Safe Client: canonical idempotency + ndjson ledger with legacy-compatible constructor."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional

from infra.idempotency import execute_once
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
from synapse.infra.retry_policy import RetryPolicy
from synapse.ledger_ndjson import append_event, build_event
from synapse.meta.governed_write_anchor import attach_governed_anchor
from synapse.meta.publisher_adapter import call_create_campaign, call_pause_campaign
from synapse.meta.publisher_contracts import (
    MetaCampaignPayload,
    MetaCampaignResponse,
    MetaPauseRequest,
)


def _check_capital_shield(spend_mxn: Decimal, correlation_id: str) -> Dict[str, Any]:
    if spend_mxn <= 0:
        return {
            "gate": "capital_shield",
            "allowed": True,
            "reason": "zero_spend_allowed",
            "correlation_id": correlation_id,
        }

    try:
        from ops.capital_shield_v2 import CapitalShieldV2  # type: ignore[import-untyped]
    except ImportError:
        return {
            "gate": "capital_shield",
            "allowed": False,
            "reason": "module_unavailable_BLOCKED",
            "correlation_id": correlation_id,
        }

    try:
        from vault.vault_file_backed import VaultFileBacked  # type: ignore[import-untyped]
        vault = VaultFileBacked()
    except (OSError, ValueError, TypeError, ArithmeticError, ImportError, RuntimeError) as exc:
        import logging as _log

        _log.getLogger(__name__).critical("VAULT_LOAD_FAILED: %s - blocking spend", exc)
        return {
            "gate": "capital_shield",
            "allowed": False,
            "reason": f"vault_load_failed:{type(exc).__name__}",
            "correlation_id": correlation_id,
        }

    try:
        shield = CapitalShieldV2(vault=vault)
        decision = shield.decide_for_product(
            final_decision="approved",
            requested_amount=spend_mxn,
        )
    except (OSError, ValueError, TypeError, ArithmeticError, ImportError, RuntimeError) as exc:
        return {
            "gate": "capital_shield",
            "allowed": False,
            "reason": f"gate_execution_error:{type(exc).__name__}",
            "correlation_id": correlation_id,
        }

    return {
        "gate": "capital_shield",
        "allowed": decision.reason == "approved",
        "allocated": str(decision.allocated),
        "reason": decision.reason,
        "correlation_id": correlation_id,
    }


def _check_safety_middleware(spend_mxn: Decimal, correlation_id: str) -> Dict[str, Any]:
    if spend_mxn <= 0:
        return {
            "gate": "safety_middleware",
            "allowed": True,
            "reason": "zero_spend_allowed",
            "correlation_id": correlation_id,
        }

    try:
        from ops.safety_middleware import check_safety_before_spend  # type: ignore[import-untyped]
    except ImportError:
        return {
            "gate": "safety_middleware",
            "allowed": False,
            "reason": "module_unavailable_BLOCKED",
            "correlation_id": correlation_id,
        }

    try:
        result = check_safety_before_spend(amount=spend_mxn, operation_id=correlation_id)
        is_ok = bool(getattr(result, "is_ok", lambda: bool(result))())
    except (OSError, ValueError, TypeError, ArithmeticError, ImportError, RuntimeError) as exc:
        return {
            "gate": "safety_middleware",
            "allowed": False,
            "reason": f"gate_execution_error:{type(exc).__name__}",
            "correlation_id": correlation_id,
        }

    return {
        "gate": "safety_middleware",
        "allowed": is_ok,
        "reason": "passed" if is_ok else str(result),
        "correlation_id": correlation_id,
    }


def _generate_mock_id(idempotency_key: str) -> str:
    h = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"MOCK_CAMP_{h}"


def _coerce_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_campaign_contract(payload: Dict[str, Any]) -> MetaCampaignPayload:
    targeting = payload.get("targeting")
    promoted_object = payload.get("promoted_object")

    targeting_dict = dict(targeting) if isinstance(targeting, Mapping) else None
    promoted_object_dict = dict(promoted_object) if isinstance(promoted_object, Mapping) else None

    handled = {
        "name",
        "objective",
        "status",
        "budget_mxn",
        "daily_budget_minor_units",
        "targeting",
        "promoted_object",
    }
    extra = {k: v for k, v in payload.items() if k not in handled}

    return MetaCampaignPayload(
        name=str(payload.get("name", "")),
        objective=str(payload.get("objective", "OUTCOME_SALES")),
        status="PAUSED",
        budget_mxn=_coerce_decimal(payload.get("budget_mxn")),
        daily_budget_minor_units=_coerce_int(payload.get("daily_budget_minor_units")),
        targeting=targeting_dict,
        promoted_object=promoted_object_dict,
        extra=extra,
    )


def _normalize_api_response(api_result: Any) -> Dict[str, Any]:
    if isinstance(api_result, MetaCampaignResponse):
        out: Dict[str, Any] = {
            "ok": api_result.ok,
            "campaign_id": api_result.campaign_id,
            "status": api_result.status,
            "mode": api_result.mode,
        }
        if api_result.api_response is not None:
            out["api_response"] = dict(api_result.api_response)
        if api_result.error_code is not None:
            out["error_code"] = api_result.error_code
        if api_result.error_message is not None:
            out["error_message"] = api_result.error_message
        return out

    if isinstance(api_result, Mapping):
        return dict(api_result)

    return {"raw_response": str(api_result)}


def _extract_path(value: Any, field_name: str) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    path = getattr(value, "path", None)
    if isinstance(path, Path):
        return path
    if isinstance(path, str):
        return Path(path)
    raise TypeError(f"{field_name}_must_be_path_or_have_path_attr")


def _sqlite_sidecar(path: Path) -> Path:
    suffix = path.suffix.lower()
    if suffix in {".sqlite3", ".sqlite", ".db"}:
        return path
    if suffix:
        return path.with_suffix(".sqlite3")
    return path.with_name(f"{path.name}.sqlite3")


def _allow_mock_module_unavailable(result: Dict[str, Any], *, is_live: bool) -> Dict[str, Any]:
    if is_live:
        return result
    if str(result.get("reason", "")).strip() == "module_unavailable_BLOCKED":
        patched = dict(result)
        patched["allowed"] = True
        patched["reason"] = "module_unavailable_ALLOWED_IN_MOCK"
        return patched
    return result


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
    feature_flags: FeatureFlags
    retry_policy: RetryPolicy
    circuit_breaker: CircuitBreaker
    idempotency_store: Any
    ledger: Any
    config: MetaSafeClientConfig = field(default_factory=MetaSafeClientConfig)

    @property
    def _is_live(self) -> bool:
        return self.feature_flags.is_on("meta_live_api", default=False)

    @property
    def _idempotency_db_path(self) -> Path:
        return _sqlite_sidecar(_extract_path(self.idempotency_store, "idempotency_store"))

    @property
    def _ledger_path(self) -> Path:
        return _extract_path(self.ledger, "ledger")

    def _append_governed_event(
        self,
        *,
        event_type: str,
        correlation_id: str,
        idempotency_key: str,
        severity: str,
        payload: Dict[str, Any],
        critical: bool = False,
    ) -> None:
        governed_payload = attach_governed_anchor(
            event_type=event_type,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload=payload,
            severity=severity,
            critical=critical,
            event_id=correlation_id,
        )
        record = build_event(
            kind=event_type,
            payload=governed_payload,
            event_id=f"{correlation_id}:{event_type}",
        )
        record["event_type"] = event_type
        record["correlation_id"] = correlation_id
        record["idempotency_key"] = idempotency_key
        record["severity"] = severity
        record["critical"] = bool(critical)
        append_event(record, path=self._ledger_path)

    def _recover_governed_payload(
        self,
        *,
        event_types: tuple[str, ...],
        idempotency_key: str,
        correlation_id: str,
    ) -> Optional[Dict[str, Any]]:
        import json
        from pathlib import Path

        ledger_path = Path(self._ledger_path)
        if not ledger_path.exists():
            return None

        try:
            lines = ledger_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return None

        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

            if str(record.get("event_type", "")) not in event_types:
                continue
            if str(record.get("idempotency_key", "")) != idempotency_key:
                continue
            if str(record.get("correlation_id", "")) != correlation_id:
                continue

            payload = record.get("payload")
            if isinstance(payload, Mapping):
                return dict(payload)

        return None

    def _recover_idempotent_result(
        self,
        *,
        event_types: tuple[str, ...],
        idempotency_key: str,
        correlation_id: str,
        status: str,
        fallback_mode: str,
    ) -> Optional[Dict[str, Any]]:
        recovered = self._recover_governed_payload(
            event_types=event_types,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        if recovered is None:
            return None

        result = dict(recovered)
        result.setdefault("idempotency_key", idempotency_key)
        result.setdefault("correlation_id", correlation_id)
        result.setdefault("mode", fallback_mode)
        result["recovered_from"] = "governed_ledger"
        result["idempotency_status"] = status
        return result

    def create_campaign_safe(
        self,
        payload: Dict[str, Any] | MetaCampaignPayload,
        idempotency_key: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        if isinstance(payload, MetaCampaignPayload):
            payload = payload.to_api_dict()
        else:
            payload = dict(payload)

        payload["status"] = "PAUSED"

        budget_mxn = _coerce_decimal(payload.get("budget_mxn")) or Decimal("0")
        cs_result = _allow_mock_module_unavailable(
            _check_capital_shield(budget_mxn, correlation_id),
            is_live=self._is_live,
        )
        sm_result = _allow_mock_module_unavailable(
            _check_safety_middleware(budget_mxn, correlation_id),
            is_live=self._is_live,
        )

        if not cs_result["allowed"] or not sm_result["allowed"]:
            blocked_by = []
            blocked_details = []
            if not cs_result["allowed"]:
                blocked_by.append("capital_shield")
                blocked_details.append(
                    f"capital_shield:{str(cs_result.get('reason', 'unknown'))}"
                )
            if not sm_result["allowed"]:
                blocked_by.append("safety_middleware")
                blocked_details.append(
                    f"safety_middleware:{str(sm_result.get('reason', 'unknown'))}"
                )
            result: Dict[str, Any] = {
                "ok": False,
                "error_code": "pre_spend_gate_blocked",
                "blocked_by": blocked_by,
                "capital_shield": cs_result,
                "safety_middleware": sm_result,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            }
            self._append_governed_event(
                event_type="meta.create_campaign.blocked",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                severity="WARN",
                payload=result,
                critical=True,
            )
            try:
                from synapse.infra.alert_wiring import get_alert_sink

                sink = get_alert_sink()
                sink.send(
                    f"SPEND BLOCKED by {','.join(blocked_by)} "
                    f"details={';'.join(blocked_details)} "
                    f"budget={budget_mxn} corr={correlation_id}",
                    level="WARN",
                    dedupe_key=f"spend_blocked:{correlation_id}",
                )
            except Exception:
                pass
            return result

        operation_payload = {
            "operation": "meta.create_campaign_safe",
            "live": self._is_live,
            "payload": payload,
        }

        def _operation(_: Any) -> Dict[str, Any]:
            self._append_governed_event(
                event_type="meta.create_campaign.attempt",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                severity="INFO",
                payload={"live": self._is_live, "campaign_payload": payload},
                critical=True,
            )

            if not self._is_live:
                mock_id = _generate_mock_id(idempotency_key)
                result = {
                    "ok": True,
                    "mode": "mock",
                    "campaign_id": mock_id,
                    "status": "PAUSED",
                    "idempotency_key": idempotency_key,
                    "correlation_id": correlation_id,
                }
                self._append_governed_event(
                    event_type="meta.create_campaign.result",
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    severity="INFO",
                    payload=result,
                    critical=True,
                )
                try:
                    from synapse.infra.alert_wiring import get_alert_sink

                    sink = get_alert_sink()
                    sink.send(
                        f"CREATE_CAMPAIGN mode={result['mode']} "
                        f"status={result['status']} "
                        f"campaign_id={result['campaign_id']} "
                        f"corr={correlation_id}",
                        level="INFO",
                        dedupe_key=f"create_campaign:{correlation_id}",
                    )
                except Exception:
                    pass
                return result

            campaign_contract = _to_campaign_contract(payload)

            def _do_create() -> Any:
                return self.circuit_breaker.call(lambda: call_create_campaign(campaign_contract))

            api_result = self.retry_policy.run(_do_create)
            api_payload = _normalize_api_response(api_result)

            result = {
                "ok": True,
                "mode": "live",
                "campaign_id": api_payload.get("campaign_id") or api_payload.get("id"),
                "status": str(api_payload.get("status", "PAUSED")),
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
                "api_response": api_payload,
            }
            self._append_governed_event(
                event_type="meta.create_campaign.result",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                severity="INFO",
                payload=result,
                critical=True,
            )
            try:
                from synapse.infra.alert_wiring import get_alert_sink

                sink = get_alert_sink()
                sink.send(
                    f"CREATE_CAMPAIGN mode={result['mode']} "
                    f"status={result['status']} "
                    f"campaign_id={result['campaign_id']} "
                    f"corr={correlation_id}",
                    level="INFO",
                    dedupe_key=f"create_campaign:{correlation_id}",
                )
            except Exception:
                pass
            return result

        try:
            idem_result = execute_once(
                key=idempotency_key,
                payload=operation_payload,
                operation=_operation,
                db_path=self._idempotency_db_path,
            )
        except CircuitOpenError as exc:
            return self._handle_error(exc, idempotency_key, correlation_id, error_code="circuit_open")
        except (OSError, ValueError, TypeError, ArithmeticError, KeyError, NotImplementedError) as exc:
            return self._handle_error(exc, idempotency_key, correlation_id, error_code="create_campaign_error")

        status = str(idem_result.get("status") or "").strip().upper()
        response = idem_result.get("response")
        response_dict = dict(response) if isinstance(response, Mapping) else {}

        if status == "COMPLETED":
            return response_dict

        if status == "DUPLICATE":
            return {
                "ok": True,
                "mode": "cached",
                "campaign_id": response_dict.get("campaign_id"),
                "status": response_dict.get("status"),
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
                "result": response_dict,
            }

        if status in {"CONFLICT", "IN_FLIGHT"}:
            recovered = self._recover_idempotent_result(
                event_types=("meta.create_campaign.result",),
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                status=status,
                fallback_mode="recovered",
            )
            if recovered is not None:
                return recovered

        if status == "CONFLICT":
            return self._handle_error(
                RuntimeError("idempotency_conflict"),
                idempotency_key,
                correlation_id,
                error_code="idempotency_conflict",
            )

        if status == "IN_FLIGHT":
            return self._handle_error(
                RuntimeError("idempotency_in_flight"),
                idempotency_key,
                correlation_id,
                error_code="idempotency_in_flight",
            )

        return self._handle_error(
            RuntimeError(f"unexpected_idempotency_status:{status or '<empty>'}"),
            idempotency_key,
            correlation_id,
            error_code="idempotency_unexpected_status",
        )

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

        operation_payload = {
            "operation": "meta.maybe_autopause",
            "live": self._is_live,
            "spend_today_mxn": str(spend_today_mxn),
            "cap_mxn": str(cap_mxn),
            "threshold_mxn": str(threshold),
            "should_pause": should_pause,
            "campaign_id": campaign_id,
        }

        def _operation(_: Any) -> Dict[str, Any]:
            self._append_governed_event(
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
                critical=True,
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
                self._append_governed_event(
                    event_type="meta.autopause.result",
                    correlation_id=correlation_id,
                    idempotency_key=idem_key,
                    severity="INFO",
                    payload=result,
                    critical=True,
                )
                return result

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
                self._append_governed_event(
                    event_type="meta.autopause.result",
                    correlation_id=correlation_id,
                    idempotency_key=idem_key,
                    severity="WARN",
                    payload=result,
                    critical=True,
                )
                try:
                    from synapse.infra.alert_wiring import get_alert_sink

                    sink = get_alert_sink()
                    sink.send(
                        f"AUTOPAUSE action={result['action']} "
                        f"mode={result['mode']} "
                        f"reason={result['reason']} "
                        f"spend={result['spend_today_mxn']} "
                        f"threshold={result['threshold_mxn']} "
                        f"campaign_id={campaign_id} "
                        f"corr={correlation_id}",
                        level="WARN",
                        dedupe_key=f"autopause:{correlation_id}",
                    )
                except Exception:
                    pass
                return result

            pause_request = MetaPauseRequest(campaign_id=campaign_id)

            def _do_pause() -> Any:
                return self.circuit_breaker.call(lambda: call_pause_campaign(pause_request))

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
            self._append_governed_event(
                event_type="meta.autopause.result",
                correlation_id=correlation_id,
                idempotency_key=idem_key,
                severity="WARN",
                payload=result,
                critical=True,
            )
            try:
                from synapse.infra.alert_wiring import get_alert_sink

                sink = get_alert_sink()
                sink.send(
                    f"AUTOPAUSE action={result['action']} "
                    f"mode={result['mode']} "
                    f"reason={result['reason']} "
                    f"spend={result['spend_today_mxn']} "
                    f"threshold={result['threshold_mxn']} "
                    f"campaign_id={campaign_id} "
                    f"corr={correlation_id}",
                    level="WARN",
                    dedupe_key=f"autopause:{correlation_id}",
                )
            except Exception:
                pass
            return result

        try:
            idem_result = execute_once(
                key=idem_key,
                payload=operation_payload,
                operation=_operation,
                db_path=self._idempotency_db_path,
            )
        except CircuitOpenError as exc:
            return self._handle_error(exc, idem_key, correlation_id, error_code="circuit_open")
        except Exception as exc:
            return self._handle_error(exc, idem_key, correlation_id, error_code="autopause_error")

        status = str(idem_result.get("status") or "").strip().upper()
        response = idem_result.get("response")
        response_dict = dict(response) if isinstance(response, Mapping) else {}

        if status == "COMPLETED":
            return response_dict

        if status == "DUPLICATE":
            return {
                "ok": True,
                "mode": "cached",
                "action": response_dict.get("action"),
                "reason": response_dict.get("reason"),
                "campaign_id": response_dict.get("campaign_id"),
                "idempotency_key": idem_key,
                "correlation_id": correlation_id,
                "result": response_dict,
            }

        if status in {"CONFLICT", "IN_FLIGHT"}:
            recovered = self._recover_idempotent_result(
                event_types=("meta.autopause.result",),
                idempotency_key=idem_key,
                correlation_id=correlation_id,
                status=status,
                fallback_mode="recovered",
            )
            if recovered is not None:
                return recovered

        if status == "CONFLICT":
            return self._handle_error(RuntimeError("idempotency_conflict"), idem_key, correlation_id, error_code="idempotency_conflict")

        if status == "IN_FLIGHT":
            return self._handle_error(RuntimeError("idempotency_in_flight"), idem_key, correlation_id, error_code="idempotency_in_flight")

        return self._handle_error(
            RuntimeError(f"unexpected_idempotency_status:{status or '<empty>'}"),
            idem_key,
            correlation_id,
            error_code="idempotency_unexpected_status",
        )

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
        self._append_governed_event(
            event_type="meta.error",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            severity="ERROR",
            payload=result,
            critical=True,
        )
        try:
            from synapse.infra.alert_wiring import get_alert_sink

            sink = get_alert_sink()
            sink.send(
                f"META ERROR: code={error_code} "
                f"type={type(exc).__name__} "
                f"corr={correlation_id} "
                f"idem={idempotency_key} "
                f"msg={str(exc)[:100]}",
                level="ERROR",
                dedupe_key=f"meta_error:{error_code}:{correlation_id}",
            )
        except Exception:
            pass
        return result
