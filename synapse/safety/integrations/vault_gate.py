from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from infra.vault import Vault
from synapse.safety.limits import RiskLimits, RiskSnapshot
from synapse.safety.safe_execute import SafeExecuteResult, safe_execute


@dataclass(frozen=True)
class VaultGateConfig:
    """
    Policy mínima para usar SafetyGate con Vault.

    Nota: SafetyCore v1 interpreta daily_loss relativo vs monthly_budget.
    Aquí tratamos amount como "peor caso" de pérdida del día para bloquear
    requests que excedan el límite relativo.
    """
    limits: RiskLimits
    expected_spend_rate_4h: float = 1.0
    actual_spend_4h: float = 1.0


def _to_float(x: Any) -> float:
    if isinstance(x, Decimal):
        return float(x)
    return float(x)


def request_spend_with_gate(
    *,
    vault: Vault,
    amount: Decimal,
    bucket: str,
    cfg: VaultGateConfig,
) -> SafeExecuteResult:
    """
    Envuelve vault.request_spend(...) con SafetyGate.
    Si tripea: NO se ejecuta request_spend.
    """
    monthly_budget = _to_float(getattr(vault, "total_budget"))
    snap = RiskSnapshot(
        monthly_budget=monthly_budget,
        expected_spend_rate_4h=cfg.expected_spend_rate_4h,
        actual_spend_4h=cfg.actual_spend_4h,
        daily_loss=_to_float(amount),
    )

    def action():
        return vault.request_spend(amount, bucket=bucket)

    return safe_execute(snapshot=snap, limits=cfg.limits, action=action)