from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Optional

import logging
logger = logging.getLogger(__name__)

from infra.result import Ok, Err, Result
from synapse.safety.circuit import CircuitBreaker
from synapse.safety.gate import run_safety_gate, SafetyGateTripped
from synapse.safety.killswitch import KillSwitch, KillSwitchActivation, KillSwitchLevel
from synapse.safety.limits import RiskLimits, RiskSnapshot

_DEFAULT_KILLSWITCH_FILE = Path(os.getenv("SYNAPSE_KILLSWITCH_FILE", "data/safety/killswitch.json"))


def _ensure_killswitch(killswitch: Optional[KillSwitch]) -> KillSwitch:
    if killswitch is not None:
        return killswitch
    return KillSwitch(state_file=_DEFAULT_KILLSWITCH_FILE)


def check_safety_before_spend(
    amount: Decimal,
    operation_id: str,
    killswitch: Optional[KillSwitch] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    risk_snapshot: Optional[RiskSnapshot] = None,
    risk_limits: Optional[RiskLimits] = None,
    trip_system_killswitch_on_gate: bool = True,
) -> Result:
    """
    Money-path safety checks (FAIL-CLOSED).

    1) KillSwitch (file-backed preferred).
    2) CircuitBreaker.
    3) SafetyGate (RiskLimits/RiskSnapshot) when provided.
    """
    ks = _ensure_killswitch(killswitch)

    # 1) KillSwitch
    if ks.is_active(KillSwitchLevel.SYSTEM):
        reason = f"KILLSWITCH_ACTIVE: system-level kill switch is on for op={operation_id} amount={amount}"
        logger.warning(reason)
        return Err(reason)
    logger.debug("killswitch check passed for op=%s", operation_id)

    # 2) CircuitBreaker
    if circuit_breaker is not None:
        if not circuit_breaker.can_execute():
            reason = f"CIRCUIT_OPEN: circuit breaker is {circuit_breaker.state.value} for op={operation_id} amount={amount}"
            logger.warning(reason)
            return Err(reason)
        logger.debug("circuit_breaker check passed for op=%s", operation_id)

    # 3) SafetyGate (only if we have full inputs)
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

    # All checks passed
    logger.info("safety checks passed for op=%s amount=%s", operation_id, amount)
    return Ok(True)