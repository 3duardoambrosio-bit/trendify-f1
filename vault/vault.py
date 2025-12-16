from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from core.result import Ok, Err, Result


BudgetType = Literal["learning", "operational", "reserve"]


@dataclass(frozen=True)
class SpendApproval:
    """
    Aprobación de gasto desde el Vault.
    """
    amount: Decimal
    budget_type: BudgetType


@dataclass(frozen=True)
class SpendError:
    """
    Error al intentar gastar desde el Vault.
    """
    message: str
    budget_type: Optional[BudgetType] = None


@dataclass
class Vault:
    """
    Vault con 3 buckets de capital:

    - learning_budget: para probar productos nuevos (ej. 30%).
    - operational_budget: para escalar ganadores (ej. 55%).
    - reserve_budget: 100% intocable (ej. 15%).

    Invariantes:
    - Todos los budgets son >= 0.
    - learning_budget + operational_budget + reserve_budget = total_budget.
    - reserve_budget nunca se puede gastar vía request_spend.
    """

    total_budget: Decimal
    learning_budget: Decimal
    operational_budget: Decimal
    reserve_budget: Decimal

    learning_spent: Decimal = Decimal("0")
    operational_spent: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        try:
            self.total_budget = Decimal(self.total_budget)
            self.learning_budget = Decimal(self.learning_budget)
            self.operational_budget = Decimal(self.operational_budget)
            self.reserve_budget = Decimal(self.reserve_budget)
            self.learning_spent = Decimal(self.learning_spent)
            self.operational_spent = Decimal(self.operational_spent)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid decimal value in Vault config: {exc}") from exc

        for name, value in [
            ("total_budget", self.total_budget),
            ("learning_budget", self.learning_budget),
            ("operational_budget", self.operational_budget),
            ("reserve_budget", self.reserve_budget),
        ]:
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

        if self.learning_budget + self.operational_budget + self.reserve_budget != self.total_budget:
            raise ValueError(
                "Vault budgets must sum exactly to total_budget "
                f"(learning + operational + reserve = {self.learning_budget + self.operational_budget + self.reserve_budget}, "
                f"total_budget = {self.total_budget})"
            )

        if self.learning_spent < 0 or self.operational_spent < 0:
            raise ValueError("Spent amounts must be non-negative")

        if self.learning_spent > self.learning_budget:
            raise ValueError("learning_spent cannot exceed learning_budget")

        if self.operational_spent > self.operational_budget:
            raise ValueError("operational_spent cannot exceed operational_budget")

    # --- Properties de conveniencia ---

    @property
    def total_spent(self) -> Decimal:
        return self.learning_spent + self.operational_spent

    @property
    def learning_remaining(self) -> Decimal:
        return self.learning_budget - self.learning_spent

    @property
    def operational_remaining(self) -> Decimal:
        return self.operational_budget - self.operational_spent

    @property
    def reserve_intact(self) -> bool:
        """
        Invariante fundamental:
        - reserve_budget nunca se toca vía request_spend.
        """
        return True

    # --- Core API ---

    def request_spend(
        self,
        amount: Decimal,
        budget_type: BudgetType,
    ) -> Result[SpendApproval, SpendError]:
        """
        Solicita gastar `amount` desde uno de los budgets.

        Reglas:
        - amount debe ser > 0.
        - budget_type = "learning" | "operational" | "reserve".
        - "reserve" SIEMPRE devuelve Err: no se puede gastar.
        - Nunca se permite que learning_spent u operational_spent
          excedan sus budgets.
        """

        try:
            dec_amount = Decimal(amount)
        except InvalidOperation:
            return Err(SpendError("Invalid amount", budget_type=budget_type))

        if dec_amount <= 0:
            return Err(SpendError("Amount must be positive", budget_type=budget_type))

        if budget_type == "reserve":
            return Err(
                SpendError(
                    message="Reserve budget is untouchable",
                    budget_type="reserve",
                )
            )

        if budget_type == "learning":
            if self.learning_spent + dec_amount > self.learning_budget:
                return Err(
                    SpendError(
                        message="Learning budget exceeded",
                        budget_type="learning",
                    )
                )
            self.learning_spent += dec_amount  # type: ignore[assignment]
            return Ok(
                SpendApproval(
                    amount=dec_amount,
                    budget_type="learning",
                )
            )

        if budget_type == "operational":
            if self.operational_spent + dec_amount > self.operational_budget:
                return Err(
                    SpendError(
                        message="Operational budget exceeded",
                        budget_type="operational",
                    )
                )
            self.operational_spent += dec_amount  # type: ignore[assignment]
            return Ok(
                SpendApproval(
                    amount=dec_amount,
                    budget_type="operational",
                )
            )

        # Esto no debería pasar nunca si se respeta BudgetType,
        # pero dejamos un guardrail defensivo.
        return Err(
            SpendError(
                message=f"Unknown budget_type: {budget_type}",
                budget_type=budget_type,
            )
        )
