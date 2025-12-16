from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


def _d(x: str | int | float | Decimal) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class CashFlowState:
    """
    Modelo mÃƒÆ’Ã‚Â­nimo, ACERO:
    - available_cash: lo que realmente puedes gastar hoy
    - held_cash: dinero retenido por pasarela (no disponible)
    - projected_refunds/chargebacks: buffer conservador (no inventes riqueza)
    - safety_buffer_cash: mÃƒÆ’Ã‚Â­nimo intocable para no asfixiarte (runway)
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

# =========================
# BACKWARD_COMPAT_EXPORTS_V2
# Guarantee legacy symbols required by SpendGatewayV2/tests:
#   CashflowConfig, CashflowState, CashflowModel
# Also provide canonical aliases if missing (CashFlowConfig/State).
# =========================
from dataclasses import dataclass
from decimal import Decimal

_g = globals()

# If canonical exists, alias legacy -> canonical.
if "CashflowConfig" not in _g and "CashFlowConfig" in _g:
    CashflowConfig = CashFlowConfig  # noqa: N816
if "CashflowState" not in _g and "CashFlowState" in _g:
    CashflowState = CashFlowState  # noqa: N816

# If neither exists, define minimal-but-correct dataclasses (safe defaults).
if "CashflowConfig" not in _g:
    @dataclass(frozen=True)
    class CashflowConfig:  # noqa: N801
        payment_hold_days: int = 14
        safety_buffer_days: int = 14

if "CashflowState" not in _g:
    @dataclass(frozen=True)
    class CashflowState:  # noqa: N801
        available_cash: Decimal = Decimal("0")
        held_cash: Decimal = Decimal("0")
        projected_refunds: Decimal = Decimal("0")
        projected_chargebacks: Decimal = Decimal("0")

        @property
        def projected_available_cash(self) -> Decimal:
            return self.available_cash - self.projected_refunds - self.projected_chargebacks

# Model alias (v1 uses state-as-model)
if "CashflowModel" not in _g:
    CashflowModel = CashflowState  # noqa: N816

# Canonical aliases (if missing) so internal code can use either casing.
if "CashFlowConfig" not in _g:
    CashFlowConfig = CashflowConfig
if "CashFlowState" not in _g:
    CashFlowState = CashflowState

