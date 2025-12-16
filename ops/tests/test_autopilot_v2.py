from decimal import Decimal

from ops.autopilot_v2 import (
    AutopilotV2,
    AutopilotContext,
    AutopilotDecision,
    SCALE_ROAS_THRESHOLD,
    MIN_SPEND_FOR_SCALING,
)


class FakeVault:
    """
    Vault de prueba:

    - Tiene un saldo inicial.
    - request_spend:
        - autoriza si amount <= remaining
        - descuenta del saldo cuando autoriza
    """

    def __init__(self, initial_budget: Decimal) -> None:
        self.initial_budget = Decimal(initial_budget)
        self.remaining = Decimal(initial_budget)
        self.calls: list[tuple[Decimal, str]] = []

    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        amount = Decimal(amount)
        self.calls.append((amount, budget_type))

        if amount <= self.remaining:
            self.remaining -= amount
            return True
        return False


def _make_ctx(
    *,
    final_decision: str = "approved",
    roas: float = 1.0,
    spend: Decimal = Decimal("0"),
    requested: Decimal = Decimal("10"),
) -> AutopilotContext:
    return AutopilotContext(
        product_id="p-test",
        final_decision=final_decision,
        current_roas=roas,
        spend=spend,
        requested_budget=requested,
    )


def test_not_approved_never_spends() -> None:
    vault = FakeVault(Decimal("100"))
    autopilot = AutopilotV2(vault=vault)

    ctx = _make_ctx(final_decision="rejected", roas=2.0, spend=Decimal("50"))
    decision = autopilot.decide(ctx)

    assert isinstance(decision, AutopilotDecision)
    assert decision.action == "hold"
    assert decision.allocated_budget == Decimal("0")
    assert decision.reason == "not_approved_by_buyer"
    # No debería ni intentar pedir presupuesto
    assert vault.calls == []


def test_insufficient_data_leads_to_test_when_budget_allows() -> None:
    """
    Poco spend (< MIN_SPEND_FOR_DECISION), pero producto aprobado
    y vault con presupuesto → el autopilot debe mandar a test.
    """
    vault = FakeVault(Decimal("100"))
    autopilot = AutopilotV2(vault=vault)

    ctx = _make_ctx(
        final_decision="approved",
        roas=0.9,
        spend=Decimal("0"),  # data insuficiente
        requested=Decimal("10"),
    )

    decision = autopilot.decide(ctx)

    assert decision.action == "test"
    assert decision.allocated_budget == Decimal("10")
    assert decision.reason == "test_within_budget"
    assert vault.remaining == Decimal("90")


def test_hard_kill_when_roas_is_trash() -> None:
    """
    Con suficiente spend y ROAS muy bajo, el autopilot debe matar
    sin siquiera intentar gastar capital.
    """
    vault = FakeVault(Decimal("100"))
    autopilot = AutopilotV2(vault=vault)

    ctx = _make_ctx(
        final_decision="approved",
        roas=0.2,  # muy por debajo del HARD_KILL_ROAS
        spend=MIN_SPEND_FOR_SCALING,  # suficiente data
        requested=Decimal("20"),
    )

    decision = autopilot.decide(ctx)

    assert decision.action == "kill"
    assert decision.allocated_budget == Decimal("0")
    assert decision.reason == "kill_rule_triggered"
    assert vault.remaining == Decimal("100")  # nunca tocó el vault


def test_pause_when_roas_in_gray_zone() -> None:
    """
    ROAS en la zona gris entre hard y soft → pause.
    """
    vault = FakeVault(Decimal("100"))
    autopilot = AutopilotV2(vault=vault)

    mid_roas = (0.7 + 1.0) / 2.0  # entre hard y soft, coordinado con exit_criteria_v2

    ctx = _make_ctx(
        final_decision="approved",
        roas=mid_roas,
        spend=MIN_SPEND_FOR_SCALING,
        requested=Decimal("20"),
    )

    decision = autopilot.decide(ctx)

    assert decision.action == "pause"
    assert decision.allocated_budget == Decimal("0")
    assert decision.reason == "pause_rule_triggered"
    assert vault.remaining == Decimal("100")


def test_scale_when_roas_high_and_spend_sufficient() -> None:
    """
    ROAS alto y spend razonable → el autopilot debe inclinarse por 'scale'.
    """
    vault = FakeVault(Decimal("100"))
    autopilot = AutopilotV2(vault=vault)

    ctx = _make_ctx(
        final_decision="approved",
        roas=SCALE_ROAS_THRESHOLD + 0.2,
        spend=MIN_SPEND_FOR_SCALING + Decimal("10"),
        requested=Decimal("15"),
    )

    decision = autopilot.decide(ctx)

    assert decision.action == "scale"
    assert decision.allocated_budget == Decimal("15")
    assert decision.reason == "scale_up_winner"
    assert vault.remaining == Decimal("85")


def test_hold_when_vault_has_insufficient_budget() -> None:
    """
    Si el vault no puede autorizar el gasto, el autopilot debe hacer hold
    aunque el ROAS sea razonable.
    """
    vault = FakeVault(Decimal("5"))  # no tiene suficiente para requested=10
    autopilot = AutopilotV2(vault=vault)

    ctx = _make_ctx(
        final_decision="approved",
        roas=1.2,
        spend=MIN_SPEND_FOR_SCALING,
        requested=Decimal("10"),
    )

    decision = autopilot.decide(ctx)

    assert decision.action == "hold"
    assert decision.allocated_budget == Decimal("0")
    assert decision.reason == "insufficient_budget_from_vault"
    # Se intentó el gasto, pero quedó intacto porque no alcanza para el monto
    assert vault.remaining == Decimal("5")
