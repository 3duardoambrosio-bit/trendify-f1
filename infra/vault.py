from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from infra.result import Result, Ok, Err


Bucket = Literal["learning", "operational"]


def _to_decimal(value: Decimal | float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q2(value: Decimal) -> Decimal:
    """Redondeo a 2 decimales, estilo dinero."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class VaultSnapshot:
    """Snapshot inmutable del estado del vault para logs / análisis."""
    total_budget: Decimal
    learning_budget: Decimal
    operational_budget: Decimal
    reserve_budget: Decimal
    spent_learning: Decimal
    spent_operational: Decimal

    @property
    def total_spent(self) -> Decimal:
        return self.spent_learning + self.spent_operational

    @property
    def remaining_learning(self) -> Decimal:
        return self.learning_budget - self.spent_learning

    @property
    def remaining_operational(self) -> Decimal:
        return self.operational_budget - self.spent_operational

    @property
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
      - El caller NO trabaja con floats, sólo Decimal.
      - Todas las operaciones regresan Result, nunca rompen con excepción.
    """

    total_budget: Decimal

    learning_budget: Decimal
    operational_budget: Decimal
    reserve_budget: Decimal

    spent_learning: Decimal = Decimal("0.00")
    spent_operational: Decimal = Decimal("0.00")

    @classmethod
    def from_total(
        cls,
        total: Decimal | float | int | str,
        learning_ratio: Decimal | float | int | str = Decimal("0.30"),
        operational_ratio: Decimal | float | int | str = Decimal("0.55"),
        reserve_ratio: Decimal | float | int | str = Decimal("0.15"),
    ) -> "Vault":
        total_dec = _to_decimal(total)
        lr = _to_decimal(learning_ratio)
        or_ = _to_decimal(operational_ratio)
        rr = _to_decimal(reserve_ratio)

        if lr + or_ + rr != Decimal("1"):
            raise ValueError("Las proporciones deben sumar exactamente 1.0")

        learning_budget = _q2(total_dec * lr)
        operational_budget = _q2(total_dec * or_)
        # Reserve = lo que falta para cuadrar a centavo
        reserve_budget = _q2(total_dec - learning_budget - operational_budget)

        return cls(
            total_budget=_q2(total_dec),
            learning_budget=learning_budget,
            operational_budget=operational_budget,
            reserve_budget=reserve_budget,
        )

    # ----------------------
    # PROPIEDADES DERIVADAS
    # ----------------------

    @property
    def total_spent(self) -> Decimal:
        return _q2(self.spent_learning + self.spent_operational)

    @property
    def remaining_learning(self) -> Decimal:
        return _q2(self.learning_budget - self.spent_learning)

    @property
    def remaining_operational(self) -> Decimal:
        return _q2(self.operational_budget - self.spent_operational)

    @property
    def remaining_total(self) -> Decimal:
        return _q2(self.total_budget - self.total_spent)

    def snapshot(self) -> VaultSnapshot:
        """Devuelve un snapshot inmutable de estado actual."""
        return VaultSnapshot(
            total_budget=self.total_budget,
            learning_budget=self.learning_budget,
            operational_budget=self.operational_budget,
            reserve_budget=self.reserve_budget,
            spent_learning=self.spent_learning,
            spent_operational=self.spent_operational,
        )

    # ----------------------
    # OPERACIONES PRINCIPALES
    # ----------------------

    def request_spend(
        self,
        amount: Decimal | float | int | str,
        bucket: Bucket,
    ) -> Result[Decimal, str]:
        """
        Intenta gastar `amount` en el bucket dado.

        - No toca jamás reserve.
        - Nunca permite que total_spent supere total_budget.
        - Si no hay suficiente en el bucket o en el total, regresa Err con mensaje.
        """
        amt = _q2(_to_decimal(amount))

        if amt <= Decimal("0"):
            return Err("amount must be > 0")

        if bucket not in ("learning", "operational"):
            return Err(f"invalid bucket: {bucket!r}")

        # Checar límite por bucket
        if bucket == "learning":
            if amt > self.remaining_learning:
                return Err("insufficient learning budget")
        else:
            if amt > self.remaining_operational:
                return Err("insufficient operational budget")

        # Checar límite total (learning + operational <= total)
        if amt > self.remaining_total:
            return Err("insufficient total budget")

        # Si todo bien, mutamos estado de forma controlada
        if bucket == "learning":
            self.spent_learning = _q2(self.spent_learning + amt)
        else:
            self.spent_operational = _q2(self.spent_operational + amt)

        return Ok(amt)

    # Helpers azucar

    def can_spend(self, amount: Decimal | float | int | str, bucket: Bucket) -> bool:
        """Check rápido sin mutar estado."""
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
