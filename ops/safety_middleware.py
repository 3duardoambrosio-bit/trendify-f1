from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Sequence

import logging
logger = logging.getLogger(__name__)

from infra.result import Ok, Err, Result
from synapse.safety.circuit import CircuitBreaker
from synapse.safety.gate import run_safety_gate, SafetyGateTripped
from synapse.safety.killswitch import KillSwitch, KillSwitchActivation, KillSwitchLevel
from synapse.safety.limits import RiskLimits, RiskSnapshot

_DEFAULT_KILLSWITCH_FILE = Path(os.getenv("SYNAPSE_KILLSWITCH_FILE", "data/safety/killswitch.json"))

ODD_WITHIN = "within_odd"
ODD_WITH_APPROVAL = "within_odd_with_approval"
ODD_OUTSIDE = "outside_odd"

SCOPE_SYSTEM = "system"
SCOPE_GLOBAL = "global"
SCOPE_PER_CHANNEL = "per_channel"
SCOPE_PER_OPERATION = "per_operation"


@dataclass(frozen=True)
class ThresholdDefinition:
    threshold_id: str
    key: str
    value: Any
    unit: str
    window: str
    owner: str = "week1_v0"


@dataclass(frozen=True)
class ODDDimensionResult:
    name: str
    state: str
    reason_code: str
    observed: Any
    threshold_id: Optional[str] = None
    threshold_value: Any = None


@dataclass(frozen=True)
class ODDEvaluation:
    state: str
    dimensions: tuple[ODDDimensionResult, ...]
    reason_codes: tuple[str, ...]
    requires_human_approval: bool
    minimal_risk_mode: bool
    kill_switch_scope: str
    kill_switch_target: Optional[str]


_REGISTRY_V0: Mapping[str, ThresholdDefinition] = MappingProxyType(
    {
        "spend_freshness_max_lag": ThresholdDefinition("TR-001", "spend_freshness_max_lag", 90, "min", "continuo"),
        "tracking_freshness_max_lag": ThresholdDefinition("TR-002", "tracking_freshness_max_lag", 30, "min", "continuo"),
        "spend_velocity_abs_cap_per_campaign": ThresholdDefinition("TR-004", "spend_velocity_abs_cap_per_campaign", Decimal("200"), "MXN/min", "rolling 5m"),
        "spend_envelope_daily_per_campaign": ThresholdDefinition("TR-006", "spend_envelope_daily_per_campaign", Decimal("1500"), "MXN", "dia"),
        "spend_envelope_daily_global": ThresholdDefinition("TR-007", "spend_envelope_daily_global", Decimal("8000"), "MXN", "dia"),
        "heartbeat_human_ack_normal": ThresholdDefinition("TR-010", "heartbeat_human_ack_normal", 30, "min", "continuo"),
        "heartbeat_degraded_after": ThresholdDefinition("TR-011", "heartbeat_degraded_after", 60, "min", "continuo"),
        "heartbeat_minimal_risk_after": ThresholdDefinition("TR-012", "heartbeat_minimal_risk_after", 120, "min", "continuo"),
        "clock_skew_max_acceptable": ThresholdDefinition("TR-018", "clock_skew_max_acceptable", 30, "seg", "por evento"),
        "kill_switch_scope_default": ThresholdDefinition("TR-031", "kill_switch_scope_default", SCOPE_PER_CHANNEL, "enum", "-"),
        "kill_switch_global_authority": ThresholdDefinition("TR-032", "kill_switch_global_authority", "human_only", "enum", "-"),
    }
)


def _ensure_killswitch(killswitch: Optional[KillSwitch]) -> KillSwitch:
    if killswitch is not None:
        return killswitch
    return KillSwitch(state_file=_DEFAULT_KILLSWITCH_FILE)


def get_threshold_registry_v0() -> Dict[str, ThresholdDefinition]:
    return dict(_REGISTRY_V0)


def get_threshold_value(key: str) -> Any:
    threshold = _REGISTRY_V0.get(key)
    if threshold is None:
        raise KeyError(f"unknown threshold key: {key}")
    return threshold.value


def resolve_kill_switch_scope(
    scope: Optional[str] = None,
    *,
    channel: Optional[str] = None,
    operation_id: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    resolved = str(scope or get_threshold_value("kill_switch_scope_default")).strip().lower()

    if resolved in {SCOPE_SYSTEM, SCOPE_GLOBAL}:
        return {"scope": resolved, "target_id": None}
    if resolved == SCOPE_PER_CHANNEL:
        return {"scope": resolved, "target_id": (channel or "unknown_channel")}
    if resolved == SCOPE_PER_OPERATION:
        return {"scope": resolved, "target_id": (operation_id or "unknown_operation")}

    raise ValueError(f"invalid kill switch scope: {resolved}")


def build_layer0_descriptor(
    *,
    component: str,
    channel: Optional[str] = None,
    operation_id: Optional[str] = None,
    scope: Optional[str] = None,
    threshold_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    resolved_scope = resolve_kill_switch_scope(scope, channel=channel, operation_id=operation_id)
    threshold_keys = tuple(threshold_keys or ())
    threshold_ids = [
        _REGISTRY_V0[key].threshold_id
        for key in threshold_keys
        if key in _REGISTRY_V0
    ]
    return {
        "layer": "L0",
        "component": component,
        "kill_switch_scope": resolved_scope["scope"],
        "kill_switch_target": resolved_scope["target_id"],
        "threshold_refs": threshold_ids,
        "global_authority": str(get_threshold_value("kill_switch_global_authority")),
    }


def _mk_dimension(
    *,
    name: str,
    state: str,
    reason_code: str,
    observed: Any,
    threshold_key: Optional[str] = None,
) -> ODDDimensionResult:
    threshold = _REGISTRY_V0.get(threshold_key) if threshold_key else None
    return ODDDimensionResult(
        name=name,
        state=state,
        reason_code=reason_code,
        observed=observed,
        threshold_id=(threshold.threshold_id if threshold else None),
        threshold_value=(threshold.value if threshold else None),
    )


def _normalize_decimal(value: Optional[Decimal | int | str]) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _compose_odd_state(dimensions: Sequence[ODDDimensionResult]) -> str:
    states = {dimension.state for dimension in dimensions}
    if ODD_OUTSIDE in states:
        return ODD_OUTSIDE
    if ODD_WITH_APPROVAL in states:
        return ODD_WITH_APPROVAL
    return ODD_WITHIN


def evaluate_odd(
    *,
    channel: Optional[str] = None,
    country: Optional[str] = None,
    currency: Optional[str] = None,
    spend_mxn: Optional[Decimal | int | str] = None,
    data_freshness_minutes: Optional[int] = None,
    tracking_freshness_minutes: Optional[int] = None,
    heartbeat_age_minutes: Optional[int] = None,
    approval_required: bool = False,
    allowed_channels: Sequence[str] = ("meta",),
    allowed_countries: Sequence[str] = ("MX",),
    allowed_currencies: Sequence[str] = ("MXN",),
    kill_switch_scope: Optional[str] = None,
    operation_id: Optional[str] = None,
) -> ODDEvaluation:
    dimensions: list[ODDDimensionResult] = []

    allowed_channels_norm = {str(x).strip().lower() for x in allowed_channels}
    allowed_countries_norm = {str(x).strip().upper() for x in allowed_countries}
    allowed_currencies_norm = {str(x).strip().upper() for x in allowed_currencies}

    channel_norm = (channel or "").strip().lower()
    country_norm = (country or "").strip().upper()
    currency_norm = (currency or "").strip().upper()
    spend_dec = _normalize_decimal(spend_mxn)

    if not channel_norm:
        dimensions.append(_mk_dimension(name="channel", state=ODD_WITH_APPROVAL, reason_code="CHANNEL_UNKNOWN_APPROVAL_REQUIRED", observed=channel))
    elif channel_norm not in allowed_channels_norm:
        dimensions.append(_mk_dimension(name="channel", state=ODD_OUTSIDE, reason_code="CHANNEL_OUTSIDE_ODD", observed=channel))
    else:
        dimensions.append(_mk_dimension(name="channel", state=ODD_WITHIN, reason_code="CHANNEL_WITHIN_ODD", observed=channel))

    if not country_norm:
        dimensions.append(_mk_dimension(name="country", state=ODD_WITH_APPROVAL, reason_code="COUNTRY_UNKNOWN_APPROVAL_REQUIRED", observed=country))
    elif country_norm not in allowed_countries_norm:
        dimensions.append(_mk_dimension(name="country", state=ODD_OUTSIDE, reason_code="COUNTRY_OUTSIDE_ODD", observed=country))
    else:
        dimensions.append(_mk_dimension(name="country", state=ODD_WITHIN, reason_code="COUNTRY_WITHIN_ODD", observed=country))

    if not currency_norm:
        dimensions.append(_mk_dimension(name="currency", state=ODD_WITH_APPROVAL, reason_code="CURRENCY_UNKNOWN_APPROVAL_REQUIRED", observed=currency))
    elif currency_norm not in allowed_currencies_norm:
        dimensions.append(_mk_dimension(name="currency", state=ODD_OUTSIDE, reason_code="CURRENCY_OUTSIDE_ODD", observed=currency))
    else:
        dimensions.append(_mk_dimension(name="currency", state=ODD_WITHIN, reason_code="CURRENCY_WITHIN_ODD", observed=currency))

    if spend_dec is None:
        dimensions.append(_mk_dimension(name="spend_envelope", state=ODD_WITH_APPROVAL, reason_code="SPEND_UNKNOWN_APPROVAL_REQUIRED", observed=spend_mxn, threshold_key="spend_envelope_daily_per_campaign"))
    elif spend_dec > Decimal(str(get_threshold_value("spend_envelope_daily_per_campaign"))):
        dimensions.append(_mk_dimension(name="spend_envelope", state=ODD_OUTSIDE, reason_code="SPEND_ABOVE_DAILY_CAMPAIGN_ENVELOPE", observed=str(spend_dec), threshold_key="spend_envelope_daily_per_campaign"))
    else:
        dimensions.append(_mk_dimension(name="spend_envelope", state=ODD_WITHIN, reason_code="SPEND_WITHIN_DAILY_CAMPAIGN_ENVELOPE", observed=str(spend_dec), threshold_key="spend_envelope_daily_per_campaign"))

    if data_freshness_minutes is None:
        dimensions.append(_mk_dimension(name="data_freshness", state=ODD_WITH_APPROVAL, reason_code="DATA_FRESHNESS_UNKNOWN_APPROVAL_REQUIRED", observed=data_freshness_minutes, threshold_key="spend_freshness_max_lag"))
    elif int(data_freshness_minutes) > int(get_threshold_value("spend_freshness_max_lag")):
        dimensions.append(_mk_dimension(name="data_freshness", state=ODD_OUTSIDE, reason_code="DATA_STALE", observed=int(data_freshness_minutes), threshold_key="spend_freshness_max_lag"))
    else:
        dimensions.append(_mk_dimension(name="data_freshness", state=ODD_WITHIN, reason_code="DATA_FRESHNESS_WITHIN_ODD", observed=int(data_freshness_minutes), threshold_key="spend_freshness_max_lag"))

    if tracking_freshness_minutes is None:
        dimensions.append(_mk_dimension(name="tracking_freshness", state=ODD_WITH_APPROVAL, reason_code="TRACKING_FRESHNESS_UNKNOWN_APPROVAL_REQUIRED", observed=tracking_freshness_minutes, threshold_key="tracking_freshness_max_lag"))
    elif int(tracking_freshness_minutes) > int(get_threshold_value("tracking_freshness_max_lag")):
        dimensions.append(_mk_dimension(name="tracking_freshness", state=ODD_OUTSIDE, reason_code="TRACKING_STALE", observed=int(tracking_freshness_minutes), threshold_key="tracking_freshness_max_lag"))
    else:
        dimensions.append(_mk_dimension(name="tracking_freshness", state=ODD_WITHIN, reason_code="TRACKING_FRESHNESS_WITHIN_ODD", observed=int(tracking_freshness_minutes), threshold_key="tracking_freshness_max_lag"))

    if heartbeat_age_minutes is None:
        dimensions.append(_mk_dimension(name="heartbeat", state=ODD_WITH_APPROVAL, reason_code="HEARTBEAT_UNKNOWN_APPROVAL_REQUIRED", observed=heartbeat_age_minutes, threshold_key="heartbeat_human_ack_normal"))
    elif int(heartbeat_age_minutes) >= int(get_threshold_value("heartbeat_minimal_risk_after")):
        dimensions.append(_mk_dimension(name="heartbeat", state=ODD_OUTSIDE, reason_code="HEARTBEAT_MINIMAL_RISK", observed=int(heartbeat_age_minutes), threshold_key="heartbeat_minimal_risk_after"))
    elif int(heartbeat_age_minutes) >= int(get_threshold_value("heartbeat_degraded_after")):
        dimensions.append(_mk_dimension(name="heartbeat", state=ODD_WITH_APPROVAL, reason_code="HEARTBEAT_DEGRADED_APPROVAL_REQUIRED", observed=int(heartbeat_age_minutes), threshold_key="heartbeat_degraded_after"))
    else:
        dimensions.append(_mk_dimension(name="heartbeat", state=ODD_WITHIN, reason_code="HEARTBEAT_WITHIN_ODD", observed=int(heartbeat_age_minutes), threshold_key="heartbeat_human_ack_normal"))

    if approval_required:
        dimensions.append(_mk_dimension(name="manual_approval", state=ODD_WITH_APPROVAL, reason_code="POLICY_APPROVAL_REQUIRED", observed=True))

    state = _compose_odd_state(dimensions)
    reason_codes = tuple(d.reason_code for d in dimensions if d.state != ODD_WITHIN)
    resolved_scope = resolve_kill_switch_scope(kill_switch_scope, channel=channel, operation_id=operation_id)

    return ODDEvaluation(
        state=state,
        dimensions=tuple(dimensions),
        reason_codes=reason_codes,
        requires_human_approval=(state == ODD_WITH_APPROVAL),
        minimal_risk_mode=(state == ODD_OUTSIDE),
        kill_switch_scope=str(resolved_scope["scope"]),
        kill_switch_target=resolved_scope["target_id"],
    )


def check_safety_before_spend(
    amount: Decimal,
    operation_id: str,
    killswitch: Optional[KillSwitch] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    risk_snapshot: Optional[RiskSnapshot] = None,
    risk_limits: Optional[RiskLimits] = None,
    trip_system_killswitch_on_gate: bool = True,
    *,
    enforce_odd: bool = False,
    channel: Optional[str] = None,
    country: Optional[str] = None,
    currency: Optional[str] = None,
    data_freshness_minutes: Optional[int] = None,
    tracking_freshness_minutes: Optional[int] = None,
    heartbeat_age_minutes: Optional[int] = None,
    kill_switch_scope: Optional[str] = None,
) -> Result:
    """
    Money-path safety checks (FAIL-CLOSED).

    1) ODD evaluator optional at middleware layer; callers may enforce explicitly for sovereign money-paths.
    2) KillSwitch (file-backed preferred).
    3) CircuitBreaker.
    4) SafetyGate (RiskLimits/RiskSnapshot) when provided.
    """
    if enforce_odd:
        odd = evaluate_odd(
            channel=channel,
            country=country,
            currency=currency,
            spend_mxn=amount,
            data_freshness_minutes=data_freshness_minutes,
            tracking_freshness_minutes=tracking_freshness_minutes,
            heartbeat_age_minutes=heartbeat_age_minutes,
            kill_switch_scope=kill_switch_scope,
            operation_id=operation_id,
        )
        if odd.state == ODD_OUTSIDE:
            reason = "ODD_OUTSIDE:" + ",".join(odd.reason_codes or ("OUTSIDE_ODD",))
            logger.warning(reason)
            return Err(reason)
        if odd.state == ODD_WITH_APPROVAL:
            reason = "ODD_APPROVAL_REQUIRED:" + ",".join(odd.reason_codes or ("APPROVAL_REQUIRED",))
            logger.warning(reason)
            return Err(reason)

    ks = _ensure_killswitch(killswitch)

    if ks.is_active(KillSwitchLevel.SYSTEM):
        reason = f"KILLSWITCH_ACTIVE: system-level kill switch is on for op={operation_id} amount={amount}"
        logger.warning(reason)
        return Err(reason)
    logger.debug("killswitch check passed for op=%s", operation_id)

    if circuit_breaker is not None:
        if not circuit_breaker.can_execute():
            reason = f"CIRCUIT_OPEN: circuit breaker is {circuit_breaker.state.value} for op={operation_id} amount={amount}"
            logger.warning(reason)
            return Err(reason)
        logger.debug("circuit_breaker check passed for op=%s", operation_id)

    if risk_snapshot is not None and risk_limits is not None:
        try:
            decision = run_safety_gate(snapshot=risk_snapshot, limits=risk_limits)
            logger.info("safety gate allowed op=%s amount=%s reason=%s", operation_id, amount, decision.reason)
        except SafetyGateTripped as e:
            reason = str(e)
            logger.error("safety gate TRIPPED op=%s amount=%s reason=%s", operation_id, amount, reason)

            if trip_system_killswitch_on_gate:
                ks.activate(KillSwitchActivation(
                    level=KillSwitchLevel.SYSTEM,
                    reason=reason,
                    triggered_by="safety_gate",
                    target_id=None,
                ))
                logger.critical("SYSTEM killswitch ACTIVATED by safety gate for op=%s", operation_id)

            return Err(reason)
        except Exception as e:
            reason = f"SAFETY_GATE_ERROR: {e.__class__.__name__}: {e}"
            logger.exception("safety gate ERROR op=%s amount=%s", operation_id, amount)
            ks.activate(KillSwitchActivation(
                level=KillSwitchLevel.SYSTEM,
                reason=reason,
                triggered_by="safety_gate_error",
                target_id=None,
            ))
            return Err(reason)

    logger.info("safety checks passed for op=%s amount=%s", operation_id, amount)
    return Ok(True)
