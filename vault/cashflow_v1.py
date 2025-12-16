from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


def _d(x: str | int | float | Decimal) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class CashFlowState:
    """
    Modelo mÃƒÂ­nimo, ACERO:
    - available_cash: lo que realmente puedes gastar hoy
    - held_cash: dinero retenido por pasarela (no disponible)
    - projected_refunds/chargebacks: buffer conservador (no inventes riqueza)
    - safety_buffer_cash: mÃƒÂ­nimo intocable para no asfixiarte (runway)
    """
    available_cash: Decimal
    held_cash: Decimal = Decimal("0")
    projected_refunds: Decimal = Decimal("0")
    projected_chargebacks: Decimal = Decimal("0")
    safety_buffer_cash: Decimal = Decimal("0")

    @property
    def net_available(self) -> Decimal:
        net = self.available_cash - self.projected_refunds - self.projected_chargebacks
        return net if net > 0 else Decimal("0")

    def can_spend(self, amount: Decimal) -> bool:
        amount = _d(amount)
        if amount <= 0:
            return False
        return (self.net_available - amount) >= self.safety_buffer_cash

    def runway_days(self, daily_burn: Decimal) -> Optional[Decimal]:
        daily_burn = _d(daily_burn)
        if daily_burn <= 0:
            return None
        return (self.net_available / daily_burn).quantize(Decimal("0.01"))

# Backward-compat alias (older modules expect CashflowModel)
CashflowModel = CashFlowState

# =========================
# BACKWARD_COMPAT_EXPORTS_V1
# Legacy API names expected by older modules/tests:
# - CashflowConfig
# - CashflowState
# - CashflowModel
# We keep the canonical names (CashFlow*) but provide aliases when missing.
# =========================
_g = globals()

if "CashflowConfig" not in _g and "CashFlowConfig" in _g:
    CashflowConfig = CashFlowConfig  # noqa: N816

if "CashflowState" not in _g and "CashFlowState" in _g:
    CashflowState = CashFlowState  # noqa: N816

# Model is an alias to the runtime state in v1
if "CashflowModel" not in _g:
    if "CashflowState" in _g:
        CashflowModel = CashflowState  # noqa: N816
    elif "CashFlowState" in _g:
        CashflowModel = CashFlowState  # noqa: N816

