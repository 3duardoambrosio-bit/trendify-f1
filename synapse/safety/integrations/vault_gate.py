from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import deal

from synapse.safety.limits import RiskLimits, RiskSnapshot
from synapse.safety.safe_execute import SafeExecuteResult, safe_execute


class _VaultLike(Protocol):
    total_budget: Any
    def request_spend(self, amount: Decimal, *, bucket: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class VaultGateConfig:
    """
    Policy mínima para usar SafetyGate con Vault.

    Nota: SafetyCore v1 interpreta daily_loss relativo vs monthly_budget.
    Aquí tratamos amount como "peor caso" de pérdida del día para bloquear
    requests que excedan el límite relativo.
    """
    limits: RiskLimits
    expected_spend_rate_4h: Decimal = Decimal("1.00")
    actual_spend_4h: Decimal = Decimal("1.00")


@deal.pre(lambda vault, amount, bucket, cfg: vault is not None, message="vault required")
@deal.pre(lambda vault, amount, bucket, cfg: isinstance(amount, Decimal), message="amount must be Decimal")
@deal.pre(lambda vault, amount, bucket, cfg: isinstance(bucket, str) and bool(bucket.strip()), message="bucket required")
@deal.pre(lambda vault, amount, bucket, cfg: cfg is not None, message="cfg required")
@deal.post(lambda result: isinstance(result, SafeExecuteResult), message="returns SafeExecuteResult")
@deal.raises(deal.PreContractError, deal.RaisesContractError)
def request_spend_with_gate(
    *,
    vault: _VaultLike,
    amount: Decimal,
    bucket: str,
    cfg: VaultGateConfig,
) -> SafeExecuteResult:
    """
    Envuelve vault.request_spend(...) con SafetyGate.
    Si tripea: NO se ejecuta request_spend.
    """
    snap = RiskSnapshot(
        monthly_budget=getattr(vault, "total_budget"),
        expected_spend_rate_4h=cfg.expected_spend_rate_4h,
        actual_spend_4h=cfg.actual_spend_4h,
        daily_loss=amount,
    )

    def action() -> Any:
        return vault.request_spend(amount, bucket=bucket)

    return safe_execute(snapshot=snap, limits=cfg.limits, action=action)
