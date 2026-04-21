# V3GAP:capital_shield_available_cash

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Tuple

logger = logging.getLogger(__name__)

BudgetDecision = Literal["approved", "not_approved", "insufficient_budget", "vault_error"]


@dataclass(frozen=True)
class CapitalDecision:
    """
    Decisión de asignación de test budget para un producto.

    - allocated: cuánto se va a gastar realmente en test.
    - reason:
        - "approved"             → se asignó el monto solicitado
        - "not_approved"         → producto no apto (buyer/quality)
        - "insufficient_budget"  → el vault no pudo autorizar el gasto
    """

    allocated: Decimal
    reason: BudgetDecision


class CapitalShieldV2:
    """
    Capa de protección de capital que se sienta encima de un "vault".

    El vault puede ser cualquier objeto que exponga:

        request_spend(amount: Decimal, budget_type: str) -> Any

    y que devuelva:
        - Algo con método .is_ok() → estilo Result Monad
        - O un bool truthy/falsy   → para stubs de tests

    Esta clase NO se preocupa por cómo está implementado el vault;
    sólo decide:
        - Si el producto no está aprobado → no gasta.
        - Si está aprobado → pide gasto al vault.
    """

    def __init__(
        self,
        vault: Any,
        default_budget_type: str = "learning",
    ) -> None:
        self._vault = vault
        self._budget_type = default_budget_type

    @staticmethod
    def _classify_result(result: Any) -> BudgetDecision:
        """
        Clasifica el resultado del vault preservando semántica útil:
        - approved            → autorización real
        - insufficient_budget → rechazo normal de presupuesto
        - vault_error         → falla/corrupción operativa del vault
        """
        if hasattr(result, "is_ok"):
            try:
                if bool(result.is_ok()):
                    return "approved"
            except Exception:
                return "vault_error"
        else:
            try:
                if bool(result):
                    return "approved"
            except Exception:
                return "vault_error"

        raw_reason = str(getattr(result, "reason", "") or "").strip().upper()

        if "CORRUPTED" in raw_reason or raw_reason.startswith("VAULT_"):
            return "vault_error"

        return "insufficient_budget"

    def decide_for_product(
        self,
        final_decision: str,
        requested_amount: Decimal,
        budget_type: str | None = None,
    ) -> CapitalDecision:
        """
        Lógica principal de protección de capital.

        Reglas:
        - Si final_decision != "approved" → allocated=0, reason="not_approved".
        - Si es "approved":
            - Se pide gasto al vault.
            - Si el vault autoriza → allocated=requested_amount, reason="approved".
            - Si el vault rechaza → allocated=0, reason="insufficient_budget".
        """
        # Normalizamos monto
        amount = Decimal(requested_amount)

        if amount < 0:
            raise ValueError("requested_amount no puede ser negativo")

        if final_decision != "approved":
            return CapitalDecision(
                allocated=Decimal("0"),
                reason="not_approved",
            )

        btype = budget_type or self._budget_type

        try:
            result = self._vault.request_spend(amount, btype)
        except Exception:
            logger.exception(
                "vault.request_spend raised for amount=%s budget_type=%s",
                amount, btype,
            )
            return CapitalDecision(
                allocated=Decimal("0"),
                reason="vault_error",
            )

        outcome = self._classify_result(result)

        if outcome == "approved":
            return CapitalDecision(
                allocated=amount,
                reason="approved",
            )

        if outcome == "vault_error":
            return CapitalDecision(
                allocated=Decimal("0"),
                reason="vault_error",
            )

        return CapitalDecision(
            allocated=Decimal("0"),
            reason="insufficient_budget",
        )

    def decide_for_product_float(
        self,
        final_decision: str,
        requested_amount: float,
        budget_type: str | None = None,
    ) -> Tuple[float, BudgetDecision]:
        """
        Helper para callers que todavía trabajan en float.

        Envuelve `decide_for_product` pero regresa (float, reason).
        """
        decision = self.decide_for_product(
            final_decision=final_decision,
            requested_amount=Decimal(str(requested_amount)),
            budget_type=budget_type,
        )
        return float(decision.allocated), decision.reason
