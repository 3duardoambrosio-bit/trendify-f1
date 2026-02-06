from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from synapse.safety.limits import RiskLimits, RiskSnapshot, evaluate_risk
import logging
logger = logging.getLogger(__name__)


class SafetyGateTripped(RuntimeError):
    pass


@dataclass(frozen=True)
class SafetyGateDecision:
    allowed: bool
    reason: str
    details: Dict[str, Any]


def _allowed_from(res: Any) -> bool:
    # 1) Campos booleanos típicos
    for k in ("ok", "allowed", "success", "passed", "is_ok", "pass_"):
        if hasattr(res, k):
            return bool(getattr(res, k))

    # 2) Inferencia por listas de fallos
    for k in ("violations", "errors", "reasons", "flags"):
        if hasattr(res, k):
            v = getattr(res, k)
            try:
                return len(v) == 0
            except Exception as e:
                logger.debug("suppressed exception", exc_info=True)

    # 3) Default conservador
    return False


def _reason_from(res: Any, *, allowed: bool) -> str:
    for k in ("reason", "message", "why", "detail", "details"):
        if hasattr(res, k):
            val = getattr(res, k)
            if isinstance(val, str) and val.strip():
                return val.strip()

    # fallback: si hay lista de violaciones, agarra la primera
    for k in ("violations", "errors", "reasons"):
        if hasattr(res, k):
            v = getattr(res, k)
            try:
                if isinstance(v, list) and v:
                    return str(v[0])
            except Exception as e:
                logger.debug("suppressed exception", exc_info=True)

    return "OK" if allowed else "RISK_VIOLATION"


def run_safety_gate(
    *,
    snapshot: RiskSnapshot,
    limits: RiskLimits,
    on_trip: Optional[Callable[[SafetyGateDecision], None]] = None,
) -> SafetyGateDecision:
    """
    Central gate: si falla, NO se permite ejecutar acciones downstream.
    """
    # Firma real: evaluate_risk(limits, snap)
    res = evaluate_risk(limits, snapshot)

    allowed = _allowed_from(res)
    reason = _reason_from(res, allowed=allowed)

    decision = SafetyGateDecision(
        allowed=allowed,
        reason=reason,
        details={
            "severity": getattr(res, "severity", None),
            "violations": getattr(res, "violations", getattr(res, "errors", getattr(res, "reasons", []))),
        },
    )

    if not decision.allowed:
        if on_trip:
            on_trip(decision)
        raise SafetyGateTripped(f"SAFETY_GATE_TRIPPED: {decision.reason}")

    return decision