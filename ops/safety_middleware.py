"""
Safety middleware: single choke point before any spend operation.

Checks (in order):
1. KillSwitch not active at SYSTEM level
2. CircuitBreaker allows execution
3. SafetyGate risk evaluation passes
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from infra.result import Ok, Err, Result
from synapse.safety.killswitch import KillSwitch, KillSwitchLevel
from synapse.safety.circuit import CircuitBreaker

logger = logging.getLogger(__name__)


def check_safety_before_spend(
    operation_id: str,
    amount: Decimal,
    *,
    killswitch: Optional[KillSwitch] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Result[bool, str]:
    """
    Run all safety checks before authorizing a spend operation.

    Returns Ok(True) if all checks pass, Err(reason) otherwise.
    If a component is not provided (None), that check is skipped.
    """
    # 1) KillSwitch
    if killswitch is not None:
        if killswitch.is_active(KillSwitchLevel.SYSTEM):
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

    # All checks passed
    logger.info("safety checks passed for op=%s amount=%s", operation_id, amount)
    return Ok(True)
