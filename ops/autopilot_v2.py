from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional

from .capital_shield_v2 import CapitalShieldV2, CapitalDecision
from .exit_criteria_v2 import (
    evaluate_kill_criteria,
    KillDecision,
    MIN_SPEND_FOR_DECISION,
    SOFT_KILL_ROAS,
)


AutopilotActionType = Literal["hold", "test", "scale", "pause", "kill"]


@dataclass(frozen=True)
class AutopilotContext:
    """
    Contexto mínimo que necesita el autopilot para decidir.

    - product_id: identificador del producto / campaña.
    - final_decision: "approved" / "rejected" / etc. (viene del buyer).
    - current_roas: ROAS observado hasta ahora.
    - spend: gasto acumulado hasta ahora.
    - requested_budget: cuánto querríamos gastar en el siguiente ciclo.
    """

    product_id: str
    final_decision: str
    current_roas: float
    spend: Decimal
    requested_budget: Decimal


@dataclass(frozen=True)
class AutopilotDecision:
    """
    Decisión del autopilot para el próximo ciclo.

    - action:
        - "hold"   → no mover nada / no asignar más presupuesto
        - "test"   → asignar presupuesto de prueba normal
        - "scale"  → asignar presupuesto para escalar
        - "pause"  → pausar y revisar (no matar, pero no seguir gastando)
        - "kill"   → matar, no más presupuesto

    - allocated_budget: cuánto se va a gastar realmente.
    - kill_decision: salida cruda de evaluate_kill_criteria (si se evaluó).
    - capital_decision: salida cruda de CapitalShieldV2 (si se evaluó).
    - reason: texto legible para bitácora / dashboards.
    """

    action: AutopilotActionType
    allocated_budget: Decimal
    kill_decision: Optional[KillDecision]
    capital_decision: Optional[CapitalDecision]
    reason: str


# Parámetros fundacionales para escalado
SCALE_ROAS_THRESHOLD: float = 1.5
MIN_SPEND_FOR_SCALING: Decimal = MIN_SPEND_FOR_DECISION * Decimal("2")


class AutopilotV2:
    """
    Orquestador entre kill rules y capital.

    Flujo mental:

    1) Si el producto no está aprobado por buyer/quality:
       - Nunca gasta → action="hold" con reason="not_approved_by_buyer".

    2) Si está aprobado:
       - Miramos kill rules (ROAS + spend).
       - Si kill → action="kill".
       - Si pause → action="pause".
       - Si continue:
           - Pedimos presupuesto al Vault vía CapitalShieldV2.
           - Si no hay presupuesto → "hold".
           - Si hay presupuesto:
               - Si ROAS alto y suficiente spend → "scale".
               - Si no → "test".
    """

    def __init__(self, vault: object, default_budget_type: str = "learning") -> None:
        self._vault = vault
        self._shield = CapitalShieldV2(vault=vault, default_budget_type=default_budget_type)

    def _decide_for_not_approved(self, ctx: AutopilotContext) -> AutopilotDecision:
        return AutopilotDecision(
            action="hold",
            allocated_budget=Decimal("0"),
            kill_decision=None,
            capital_decision=None,
            reason="not_approved_by_buyer",
        )

    def _decide_with_kill_rules(self, ctx: AutopilotContext) -> AutopilotDecision:
        """
        Aplica evaluate_kill_criteria y, si no mata ni pausa, pasa a capital.
        """
        kill_decision = evaluate_kill_criteria(
            roas=ctx.current_roas,
            spend=ctx.spend,
        )

        # 1) Hard kill
        if kill_decision.action == "kill":
            return AutopilotDecision(
                action="kill",
                allocated_budget=Decimal("0"),
                kill_decision=kill_decision,
                capital_decision=None,
                reason="kill_rule_triggered",
            )

        # 2) Pause
        if kill_decision.action == "pause":
            return AutopilotDecision(
                action="pause",
                allocated_budget=Decimal("0"),
                kill_decision=kill_decision,
                capital_decision=None,
                reason="pause_rule_triggered",
            )

        # 3) Continue: pasamos a capital
        return self._decide_with_capital(ctx=ctx, kill_decision=kill_decision)

    def _decide_with_capital(
        self,
        ctx: AutopilotContext,
        kill_decision: KillDecision,
    ) -> AutopilotDecision:
        """
        Usa CapitalShieldV2 para ver si el vault autoriza la prueba
        y decide entre "test", "scale" o "hold".
        """
        requested = ctx.requested_budget

        if requested <= Decimal("0"):
            # Nada solicitado, no hacemos magia.
            return AutopilotDecision(
                action="hold",
                allocated_budget=Decimal("0"),
                kill_decision=kill_decision,
                capital_decision=None,
                reason="no_budget_requested",
            )

        capital_decision = self._shield.decide_for_product(
            final_decision=ctx.final_decision,
            requested_amount=requested,
        )

        if capital_decision.allocated <= 0:
            # El vault no autorizó gasto
            # Razón puede ser not_approved o insufficient_budget
            if capital_decision.reason == "not_approved":
                reason = "not_approved_by_buyer"
            else:
                reason = "insufficient_budget_from_vault"

            return AutopilotDecision(
                action="hold",
                allocated_budget=Decimal("0"),
                kill_decision=kill_decision,
                capital_decision=capital_decision,
                reason=reason,
            )

        # Hay presupuesto autorizado.
        # Decidimos si tiene sentido "test" o "scale" según ROAS y spend.
        if (
            ctx.current_roas >= SCALE_ROAS_THRESHOLD
            and ctx.spend >= MIN_SPEND_FOR_SCALING
        ):
            action: AutopilotActionType = "scale"
            reason = "scale_up_winner"
        else:
            action = "test"
            reason = "test_within_budget"

        return AutopilotDecision(
            action=action,
            allocated_budget=capital_decision.allocated,
            kill_decision=kill_decision,
            capital_decision=capital_decision,
            reason=reason,
        )

    def decide(self, ctx: AutopilotContext) -> AutopilotDecision:
        """
        Punto único de entrada.

        Totalmente puro desde el punto de vista del caller:
        el único efecto secundario real es sobre el vault interno
        si este permite gastar (vía CapitalShieldV2).
        """
        # 0) Si buyer / quality no lo aprueba, no hay nada que hacer
        if ctx.final_decision != "approved":
            return self._decide_for_not_approved(ctx)

        # 1) Kill rules
        return self._decide_with_kill_rules(ctx)
