from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Literal, TypeAlias

import deal

from infra.result import Err, Ok, Result

Bucket = Literal["learning", "operational"]
MoneyLike: TypeAlias = Decimal | int | str


def _to_decimal(value: MoneyLike) -> Decimal:
    # Money path: accept only Decimal/int/str. Everything else -> TypeError.
    # NOTE: bool is a subclass of int; explicitly reject it.
    if isinstance(value, bool):
        raise TypeError("bool is not allowed for money")

    if isinstance(value, Decimal):
        return value

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except (AttributeError, InvalidOperation) as exc:
            raise ValueError("invalid decimal string") from exc

    raise TypeError("unsupported money type")


def _q2(value: Decimal) -> Decimal:
    """Quantize to 2 decimals, money-style."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class VaultSnapshot:
    """Snapshot inmutable del estado del vault para logs / análisis."""
    total_budget: Decimal
    learning_budget: Decimal
    operational_budget: Decimal
    reserve_budget: Decimal
    spent_learning: Decimal
    spent_operational: Decimal

    @property
    @deal.pre(lambda self: True, message="VaultSnapshot.total_spent contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="total_spent must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def total_spent(self) -> Decimal:
        return self.spent_learning + self.spent_operational

    @property
    @deal.pre(lambda self: True, message="VaultSnapshot.remaining_learning contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="remaining_learning must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def remaining_learning(self) -> Decimal:
        return self.learning_budget - self.spent_learning

    @property
    @deal.pre(lambda self: True, message="VaultSnapshot.remaining_operational contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="remaining_operational must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def remaining_operational(self) -> Decimal:
        return self.operational_budget - self.spent_operational

    @property
    @deal.pre(lambda self: True, message="VaultSnapshot.remaining_total contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="remaining_total must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def remaining_total(self) -> Decimal:
        return self.total_budget - self.total_spent


@dataclass
class Vault:
    """
    Vault de capital con tres bolsillos:
      - learning: presupuesto para testear / aprender
      - operational: presupuesto para operar lo que ya funciona
      - reserve: colchón intocable

    Invariantes clave:
      - reserve NUNCA se toca.
      - total_spent <= total_budget siempre.
      - Todo dinero se maneja con Decimal.
      - request_spend regresa Result (no lanza).
    """

    total_budget: Decimal
    learning_budget: Decimal
    operational_budget: Decimal
    reserve_budget: Decimal

    spent_learning: Decimal = Decimal("0.00")
    spent_operational: Decimal = Decimal("0.00")

    @classmethod
    @deal.pre(
        lambda cls, total, learning_ratio=Decimal("0.30"), operational_ratio=Decimal("0.55"), reserve_ratio=Decimal("0.15"): True,
        message="Vault.from_total contract",
    )
    @deal.post(lambda result: isinstance(result, Vault), message="from_total must return Vault")
    @deal.raises(ValueError, TypeError, deal.RaisesContractError)
    def from_total(
        cls,
        total: MoneyLike,
        learning_ratio: MoneyLike = Decimal("0.30"),
        operational_ratio: MoneyLike = Decimal("0.55"),
        reserve_ratio: MoneyLike = Decimal("0.15"),
    ) -> "Vault":
        total_dec_raw = _to_decimal(total)
        if total_dec_raw < Decimal("0"):
            raise ValueError("total must be >= 0")

        lr = _to_decimal(learning_ratio)
        or_ = _to_decimal(operational_ratio)
        rr = _to_decimal(reserve_ratio)

        if lr < Decimal("0") or or_ < Decimal("0") or rr < Decimal("0"):
            raise ValueError("ratios must be >= 0")

        if lr + or_ + rr != Decimal("1"):
            raise ValueError("Las proporciones deben sumar exactamente 1")

        learning_budget = _q2(total_dec_raw * lr)
        operational_budget = _q2(total_dec_raw * or_)
        reserve_budget = _q2(total_dec_raw - learning_budget - operational_budget)

        if reserve_budget < Decimal("0"):
            raise ValueError("computed reserve became negative")

        return cls(
            total_budget=_q2(total_dec_raw),
            learning_budget=learning_budget,
            operational_budget=operational_budget,
            reserve_budget=reserve_budget,
        )

    @property
    @deal.pre(lambda self: True, message="Vault.total_spent contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="total_spent must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def total_spent(self) -> Decimal:
        return _q2(self.spent_learning + self.spent_operational)

    @property
    @deal.pre(lambda self: True, message="Vault.remaining_learning contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="remaining_learning must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def remaining_learning(self) -> Decimal:
        return _q2(self.learning_budget - self.spent_learning)

    @property
    @deal.pre(lambda self: True, message="Vault.remaining_operational contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="remaining_operational must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def remaining_operational(self) -> Decimal:
        return _q2(self.operational_budget - self.spent_operational)

    @property
    @deal.pre(lambda self: True, message="Vault.remaining_total contract")
    @deal.post(lambda result: isinstance(result, Decimal), message="remaining_total must be Decimal")
    @deal.raises(deal.RaisesContractError)
    def remaining_total(self) -> Decimal:
        return _q2(self.total_budget - self.total_spent)

    @deal.pre(lambda self: True, message="Vault.snapshot contract")
    @deal.post(lambda result: isinstance(result, VaultSnapshot), message="snapshot must return VaultSnapshot")
    @deal.raises(deal.RaisesContractError)
    def snapshot(self) -> VaultSnapshot:
        return VaultSnapshot(
            total_budget=self.total_budget,
            learning_budget=self.learning_budget,
            operational_budget=self.operational_budget,
            reserve_budget=self.reserve_budget,
            spent_learning=self.spent_learning,
            spent_operational=self.spent_operational,
        )

    @deal.pre(lambda self, amount, bucket: True, message="Vault.request_spend contract")
    @deal.post(lambda result: isinstance(result, Result), message="request_spend must return Result")
    @deal.raises(deal.RaisesContractError)
    def request_spend(self, amount: MoneyLike, bucket: Bucket) -> Result[Decimal, str]:
        try:
            amt = _q2(_to_decimal(amount))
        except (TypeError, ValueError):
            return Err("invalid amount")

        if amt <= Decimal("0"):
            return Err("amount must be > 0")

        if bucket not in ("learning", "operational"):
            return Err(f"invalid bucket: {bucket!r}")

        if bucket == "learning":
            if amt > self.remaining_learning:
                return Err("insufficient learning budget")
        else:
            if amt > self.remaining_operational:
                return Err("insufficient operational budget")

        if amt > self.remaining_total:
            return Err("insufficient total budget")

        if bucket == "learning":
            self.spent_learning = _q2(self.spent_learning + amt)
        else:
            self.spent_operational = _q2(self.spent_operational + amt)

        return Ok(amt)

    @deal.pre(lambda self, amount, bucket: True, message="Vault.can_spend contract")
    @deal.post(lambda result: isinstance(result, bool), message="can_spend must return bool")
    @deal.raises(deal.RaisesContractError)
    def can_spend(self, amount: MoneyLike, bucket: Bucket) -> bool:
        tmp = self.snapshot()
        vault_clone = Vault(
            total_budget=tmp.total_budget,
            learning_budget=tmp.learning_budget,
            operational_budget=tmp.operational_budget,
            reserve_budget=tmp.reserve_budget,
            spent_learning=tmp.spent_learning,
            spent_operational=tmp.spent_operational,
        )
        result = vault_clone.request_spend(amount, bucket=bucket)
        return result.is_ok()