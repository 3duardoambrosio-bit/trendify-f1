from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

D0 = Decimal("0")

def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))

@dataclass(frozen=True)
class CashflowConfig:
    """
    Canonical config.
    safety_buffer: hard buffer de liquidez (P0).
    """
    safety_buffer: Decimal = D0

@dataclass
class CashflowState:
    """
    Canonical state.
    safety_buffer_cash: legacy buffer (compat). Se usa en State.can_spend / net_available.
    """
    available_cash: Decimal = D0
    held_cash: Decimal = D0
    projected_refunds: Decimal = D0
    projected_chargebacks: Decimal = D0
    safety_buffer_cash: Decimal = D0  # legacy compat

    def projected_available_cash(self) -> Decimal:
        net = _d(self.available_cash) - _d(self.projected_refunds) - _d(self.projected_chargebacks)
        return net if net > D0 else D0

    @property
    def net_available(self) -> Decimal:
        # legacy behavior: net = available - refunds - chargebacks - legacy_buffer (clamped >=0)
        net = self.projected_available_cash() - _d(self.safety_buffer_cash)
        return net if net > D0 else D0

    def can_spend(self, amount: Decimal) -> bool:
        amt = _d(amount)
        if amt <= D0:
            return False
        return self.net_available >= amt

    # legacy alias
    def can_debit(self, amount: Decimal) -> bool:
        return self.can_spend(amount)

    def snapshot(self) -> "CashflowState":
        return CashflowState(
            available_cash=_d(self.available_cash),
            held_cash=_d(self.held_cash),
            projected_refunds=_d(self.projected_refunds),
            projected_chargebacks=_d(self.projected_chargebacks),
            safety_buffer_cash=_d(self.safety_buffer_cash),
        )

class CashflowModel:
    """
    Canonical API consumed by SpendGatewayV2:
      - can_spend(amount)
      - snapshot()
      - debit_available(amount)

    Uses config.safety_buffer if set, else falls back to state.safety_buffer_cash (legacy).
    """
    def __init__(self, config: Optional[CashflowConfig] = None, state: Optional[CashflowState] = None):
        self.config = config or CashflowConfig()
        self.state = state or CashflowState()

    def _effective_buffer(self) -> Decimal:
        cfg = _d(self.config.safety_buffer)
        if cfg > D0:
            return cfg
        legacy = _d(self.state.safety_buffer_cash)
        return legacy if legacy > D0 else D0

    def projected_available_cash(self) -> Decimal:
        return self.state.projected_available_cash()

    def can_spend(self, amount: Decimal) -> bool:
        amt = _d(amount)
        if amt <= D0:
            return False
        return (self.projected_available_cash() - self._effective_buffer()) >= amt

    # legacy alias
    def can_debit(self, amount: Decimal) -> bool:
        return self.can_spend(amount)

    def debit_available(self, amount: Decimal) -> None:
        amt = _d(amount)
        if amt <= D0:
            return
        self.state.available_cash = _d(self.state.available_cash) - amt
        if self.state.available_cash < D0:
            self.state.available_cash = D0

    # legacy alias
    def debit(self, amount: Decimal) -> None:
        self.debit_available(amount)

    def snapshot(self) -> CashflowState:
        return self.state.snapshot()

# --- Legacy exports (older modules/tests) ---
CashFlowConfig = CashflowConfig
CashFlowState = CashflowState
CashFlowModel = CashflowModel

__all__ = [
    "CashflowConfig", "CashflowState", "CashflowModel",
    "CashFlowConfig", "CashFlowState", "CashFlowModel",
]