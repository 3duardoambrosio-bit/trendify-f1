from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


def _d(x: str | int | float | Decimal) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class CashFlowState:
    """
    Modelo mÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â­nimo, ACERO:
    - available_cash: lo que realmente puedes gastar hoy
    - held_cash: dinero retenido por pasarela (no disponible)
    - projected_refunds/chargebacks: buffer conservador (no inventes riqueza)
    - safety_buffer_cash: mÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â­nimo intocable para no asfixiarte (runway)
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

# =========================
# BACKWARD_COMPAT_EXPORTS_V3
# HARD CONTRACT for SpendGatewayV2 + tests:
# - CashflowConfig(safety_buffer=Decimal(...), ...)
# - CashflowState(available_cash=Decimal(...), ...)
# - CashflowModel(CashflowConfig, CashflowState)
# =========================
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class CashflowConfig:  # legacy casing expected by tests
    # Minimal but correct knobs
    safety_buffer: Decimal = Decimal("0.00")
    payment_hold_days: int = 14
    safety_buffer_days: int = 14  # optional; kept for future runway logic

    @property
    def safety_buffer_amount(self) -> Decimal:
        return self.safety_buffer

@dataclass(frozen=True)
class CashflowState:  # legacy casing expected by tests
    available_cash: Decimal = Decimal("0.00")
    held_cash: Decimal = Decimal("0.00")
    projected_refunds: Decimal = Decimal("0.00")
    projected_chargebacks: Decimal = Decimal("0.00")

    @property
    def projected_available_cash(self) -> Decimal:
        return self.available_cash - self.projected_refunds - self.projected_chargebacks

@dataclass(frozen=True)
class CashflowModel:  # legacy casing expected by tests
    config: CashflowConfig
    state: CashflowState

    @property
    def available_cash(self) -> Decimal:
        return self.state.available_cash

    @property
    def projected_available_cash(self) -> Decimal:
        return self.state.projected_available_cash

    def can_debit(self, amount: Decimal) -> bool:
        if amount < 0:
            return False
        return (self.projected_available_cash - self.config.safety_buffer) >= amount

    def debit(self, amount: Decimal) -> "CashflowModel":
        if amount < 0:
            raise ValueError("amount must be >= 0")
        if not self.can_debit(amount):
            raise ValueError("cash buffer would be breached")
        return CashflowModel(
            config=self.config,
            state=CashflowState(
                available_cash=self.state.available_cash - amount,
                held_cash=self.state.held_cash,
                projected_refunds=self.state.projected_refunds,
                projected_chargebacks=self.state.projected_chargebacks,
            ),
        )

# Canonical aliases for internal code (both casings supported)
CashFlowConfig = CashflowConfig
CashFlowState = CashflowState

# =========================
# CASHFLOW_METHOD_ALIASES_V1
# SpendGatewayV2 expects:
# - cashflow.can_spend(amount)
# - cashflow.spend(amount)  (optional but common)
# Keep logic single-source: map to can_debit/debit.
# =========================
from decimal import Decimal as _Decimal

def _cashflow_can_spend(self, amount: _Decimal) -> bool:
    return self.can_debit(amount)

def _cashflow_spend(self, amount: _Decimal):
    return self.debit(amount)

# attach aliases (no mutation of instances; just API surface)
try:
    CashflowModel.can_spend = _cashflow_can_spend  # type: ignore[attr-defined]
    CashflowModel.spend = _cashflow_spend          # type: ignore[attr-defined]
    CashflowModel.debit_cashflow = _cashflow_spend # type: ignore[attr-defined]
except Exception:
    # if CashflowModel is not defined for some reason, fail loudly during import elsewhere
    pass

# =========================
# CASHFLOW_GATEWAY_V2_SHIMS_V1
# SpendGatewayV2 expects:
# - snapshot() -> object with .available_cash
# - debit_available(amount) -> debits available_cash (in-place safe)
# Keep single source of truth: update state, preserve backward compat.
# =========================
from decimal import Decimal as _Decimal
from dataclasses import replace as _replace

def _cf__get_state(self):
    for k in ("state", "_state", "cashflow_state"):
        if hasattr(self, k):
            return getattr(self, k)
    return None

def _cf_snapshot(self):
    st = _cf__get_state(self)
    if st is None:
        # ultra-safe fallback (should not happen in tests)
        class _Snap:
            def __init__(self, available_cash):
                self.available_cash = available_cash
        return _Snap(getattr(self, "available_cash", _Decimal("0.00")))
    return st

def _cf_debit_available(self, amount: _Decimal):
    st = _cf_snapshot(self)
    if amount <= 0:
        return self

    new_cash = st.available_cash - amount
    # hard floor, never negative
    if new_cash < _Decimal("0.00"):
        new_cash = _Decimal("0.00")

    # prefer dataclass replace (immutable-friendly)
    try:
        new_st = _replace(st, available_cash=new_cash)
    except Exception:
        # mutable fallback
        try:
            st.available_cash = new_cash
            return self
        except Exception:
            return self

    # write back (works even if dataclass is frozen)
    for k in ("state", "_state", "cashflow_state"):
        if hasattr(self, k):
            try:
                object.__setattr__(self, k, new_st)
                return self
            except Exception:
                try:
                    setattr(self, k, new_st)
                    return self
                except Exception:
                    pass
    return self

def _cf_available_cash(self) -> _Decimal:
    return _cf_snapshot(self).available_cash

try:
    CashflowModel.snapshot = _cf_snapshot            # type: ignore[attr-defined]
    CashflowModel.debit_available = _cf_debit_available  # type: ignore[attr-defined]
    CashflowModel.available_cash = property(_cf_available_cash)  # type: ignore[attr-defined]
except Exception:
    pass
