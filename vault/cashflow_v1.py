# V3GAP:D-02_cod_rejection_in_pnl
# V3GAP:cashflow_timeline_per_payment_method
# V3GAP:A-06_payment_method_distribution
# V3GAP:A-05_msi_fee_adjustment

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

D0 = Decimal("0")


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _norm_payment_method(value: str | None) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class CashflowConfig:
    """
    Canonical config.
    safety_buffer: hard buffer de liquidez (P0).
    """
    safety_buffer: Decimal = D0


@dataclass(frozen=True)
class CashflowTimelineEntry:
    """
    Additive timeline per payment method.

    settlement_days:
        expected number of days until the method settles into available cash.
        0 means immediate / already available.

    projected_msi_fees:
        projected merchant fees attributable to MSI transactions for this method.
        A-05 must discount these fees from projected available cash.

    This structure is reporting-oriented and does NOT mutate the legacy global
    spend logic by itself; it complements the canonical state with per-method
    projected availability.
    """
    payment_method: str
    available_cash: Decimal = D0
    held_cash: Decimal = D0
    projected_refunds: Decimal = D0
    projected_chargebacks: Decimal = D0
    projected_cod_rejections: Decimal = D0
    projected_msi_fees: Decimal = D0
    settlement_days: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "payment_method", _norm_payment_method(self.payment_method))
        if int(self.settlement_days) < 0:
            raise ValueError("settlement_days must be >= 0")

    @property
    def projected_available_cash(self) -> Decimal:
        net = (
            _d(self.available_cash)
            - _d(self.projected_refunds)
            - _d(self.projected_chargebacks)
            - _d(self.projected_cod_rejections)
            - _d(self.projected_msi_fees)
        )
        return net if net > D0 else D0


@dataclass(frozen=True)
class CashflowDistributionEntry:
    """
    Distribution/reporting row derived from payment_method_timeline.
    share is normalized over projected_available_cash across methods.
    """
    payment_method: str
    projected_available_cash: Decimal = D0
    share: Decimal = D0

    def __post_init__(self) -> None:
        object.__setattr__(self, "payment_method", _norm_payment_method(self.payment_method))


@dataclass
class CashflowState:
    """
    Canonical state.

    safety_buffer_cash:
        legacy buffer (compat). Se usa en State.can_spend / net_available.

    projected_cod_rejections:
        costo proyectado por rechazos COD que aún no están materializados
        pero sí deben descontarse del cash disponible proyectado para P&L /
        spend decisions (D-02).

    projected_msi_fees:
        costo proyectado por merchant fees de MSI que debe descontarse del
        cash disponible proyectado y del P&L realista (A-05).

    payment_method_timeline:
        additive timeline/reporting surface per payment method
        (cashflow_timeline_per_payment_method).
    """
    available_cash: Decimal = D0
    held_cash: Decimal = D0
    projected_refunds: Decimal = D0
    projected_chargebacks: Decimal = D0
    safety_buffer_cash: Decimal = D0  # legacy compat
    projected_cod_rejections: Decimal = D0  # additive D-02 (tail for compat)
    projected_msi_fees: Decimal = D0  # additive A-05
    payment_method_timeline: tuple[CashflowTimelineEntry, ...] = ()

    def projected_available_cash(self) -> Decimal:
        net = (
            _d(self.available_cash)
            - _d(self.projected_refunds)
            - _d(self.projected_chargebacks)
            - _d(self.projected_cod_rejections)
            - _d(self.projected_msi_fees)
        )
        return net if net > D0 else D0

    @property
    def net_available(self) -> Decimal:
        # legacy behavior:
        # net = available - refunds - chargebacks - cod_rejections - msi_fees - legacy_buffer
        # clamped >= 0
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

    def timeline_for(self, payment_method: str) -> CashflowTimelineEntry:
        wanted = _norm_payment_method(payment_method)
        for entry in self.payment_method_timeline:
            if entry.payment_method == wanted:
                return entry
        return CashflowTimelineEntry(payment_method=wanted)

    def payment_method_distribution(self) -> tuple[CashflowDistributionEntry, ...]:
        timeline = tuple(self.payment_method_timeline)
        if not timeline:
            return ()

        totals = tuple(
            (entry.payment_method, entry.projected_available_cash)
            for entry in timeline
        )
        grand_total = sum((amount for _, amount in totals), D0)

        rows: list[CashflowDistributionEntry] = []
        for method, amount in totals:
            share = (amount / grand_total) if grand_total > D0 else D0
            rows.append(
                CashflowDistributionEntry(
                    payment_method=method,
                    projected_available_cash=amount,
                    share=share,
                )
            )
        return tuple(rows)

    def snapshot(self) -> "CashflowState":
        return CashflowState(
            available_cash=_d(self.available_cash),
            held_cash=_d(self.held_cash),
            projected_refunds=_d(self.projected_refunds),
            projected_chargebacks=_d(self.projected_chargebacks),
            safety_buffer_cash=_d(self.safety_buffer_cash),
            projected_cod_rejections=_d(self.projected_cod_rejections),
            projected_msi_fees=_d(self.projected_msi_fees),
            payment_method_timeline=tuple(
                CashflowTimelineEntry(
                    payment_method=e.payment_method,
                    available_cash=_d(e.available_cash),
                    held_cash=_d(e.held_cash),
                    projected_refunds=_d(e.projected_refunds),
                    projected_chargebacks=_d(e.projected_chargebacks),
                    projected_cod_rejections=_d(e.projected_cod_rejections),
                    projected_msi_fees=_d(e.projected_msi_fees),
                    settlement_days=int(e.settlement_days),
                )
                for e in self.payment_method_timeline
            ),
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

    def payment_method_timeline(self) -> tuple[CashflowTimelineEntry, ...]:
        return tuple(self.state.payment_method_timeline)

    def projected_available_cash_for(self, payment_method: str) -> Decimal:
        return self.state.timeline_for(payment_method).projected_available_cash

    def payment_method_distribution(self) -> tuple[CashflowDistributionEntry, ...]:
        return self.state.payment_method_distribution()

    def snapshot(self) -> CashflowState:
        return self.state.snapshot()


# --- Legacy exports (older modules/tests) ---
CashFlowConfig = CashflowConfig
CashFlowState = CashflowState
CashFlowModel = CashflowModel
CashFlowTimelineEntry = CashflowTimelineEntry
CashFlowDistributionEntry = CashflowDistributionEntry

__all__ = [
    "CashflowConfig", "CashflowState", "CashflowModel", "CashflowTimelineEntry", "CashflowDistributionEntry",
    "CashFlowConfig", "CashFlowState", "CashFlowModel", "CashFlowTimelineEntry", "CashFlowDistributionEntry",
]