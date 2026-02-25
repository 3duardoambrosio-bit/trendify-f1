from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import deal

from synapse.safety.gate import SafetyGateDecision, SafetyGateTripped, run_safety_gate
from synapse.safety.limits import RiskLimits, RiskSnapshot


@dataclass(frozen=True, slots=True)
class SafeExecuteResult:
    executed: bool
    gate: SafetyGateDecision
    result: Any = None
    error: Optional[str] = None


@deal.pre(lambda snapshot, limits, action, on_trip=None: snapshot is not None, message="snapshot required")
@deal.pre(lambda snapshot, limits, action, on_trip=None: limits is not None, message="limits required")
@deal.pre(lambda snapshot, limits, action, on_trip=None: callable(action), message="action must be callable")
@deal.pre(lambda snapshot, limits, action, on_trip=None: on_trip is None or callable(on_trip), message="on_trip must be callable or None")
@deal.post(lambda result: isinstance(result, SafeExecuteResult), message="returns SafeExecuteResult")
@deal.raises(deal.PreContractError, deal.RaisesContractError)
def safe_execute(
    *,
    snapshot: RiskSnapshot,
    limits: RiskLimits,
    action: Callable[[], Any],
    on_trip: Optional[Callable[[SafetyGateDecision], None]] = None,
) -> SafeExecuteResult:
    """
    Ejecuta action SOLO si SafetyGate permite.
    Si tripea: no ejecuta y regresa executed=False.
    """
    try:
        gate = run_safety_gate(snapshot=snapshot, limits=limits, on_trip=on_trip)
    except SafetyGateTripped as e:
        gate = SafetyGateDecision(allowed=False, reason=str(e), details={})
        return SafeExecuteResult(executed=False, gate=gate, result=None, error=str(e))

    out = action()
    return SafeExecuteResult(executed=True, gate=gate, result=out, error=None)
