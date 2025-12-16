from decimal import Decimal

from ops.capital_shield_v2 import CapitalShieldV2, CapitalDecision


class FakeVault:
    """
    Vault de prueba ultra simple.

    - Tiene un saldo inicial.
    - Cada request_spend(amount, budget_type):
        - Si amount <= remaining → descuenta y regresa True.
        - Si no → regresa False.
    """

    def __init__(self, initial_budget: Decimal) -> None:
        self.remaining = Decimal(initial_budget)
        self.calls: list[tuple[Decimal, str]] = []

    def request_spend(self, amount: Decimal, budget_type: str) -> bool:
        self.calls.append((Decimal(amount), budget_type))
        if amount <= self.remaining:
            self.remaining -= amount
            return True
        return False


def test_rejected_product_never_spends() -> None:
    vault = FakeVault(Decimal("100"))
    shield = CapitalShieldV2(vault=vault)

    decision = shield.decide_for_product(
        final_decision="rejected",
        requested_amount=Decimal("10"),
    )

    assert isinstance(decision, CapitalDecision)
    assert decision.allocated == Decimal("0")
    assert decision.reason == "not_approved"
    # El vault ni siquiera es llamado en este caso
    assert vault.remaining == Decimal("100")
    assert vault.calls == []


def test_approved_product_spends_when_vault_allows() -> None:
    vault = FakeVault(Decimal("50"))
    shield = CapitalShieldV2(vault=vault)

    decision = shield.decide_for_product(
        final_decision="approved",
        requested_amount=Decimal("20"),
    )

    assert decision.allocated == Decimal("20")
    assert decision.reason == "approved"

    # El vault fue llamado, y el saldo bajó
    assert vault.remaining == Decimal("30")
    assert vault.calls == [(Decimal("20"), "learning")]


def test_insufficient_budget_returns_zero_and_reason() -> None:
    vault = FakeVault(Decimal("15"))
    shield = CapitalShieldV2(vault=vault)

    # Primer producto: alcanza
    d1 = shield.decide_for_product(
        final_decision="approved",
        requested_amount=Decimal("10"),
    )
    # Segundo producto: ya no alcanza el monto solicitado
    d2 = shield.decide_for_product(
        final_decision="approved",
        requested_amount=Decimal("10"),
    )

    assert d1.allocated == Decimal("10")
    assert d1.reason == "approved"

    assert d2.allocated == Decimal("0")
    assert d2.reason == "insufficient_budget"

    # Invariante: nunca gastamos más de lo que había
    assert vault.remaining == Decimal("5")
    total_spent = Decimal("15") - vault.remaining
    assert total_spent <= Decimal("15")


def test_float_helper_wraps_decision_correctly() -> None:
    vault = FakeVault(Decimal("30"))
    shield = CapitalShieldV2(vault=vault)

    allocated, reason = shield.decide_for_product_float(
        final_decision="approved",
        requested_amount=5.0,
    )

    assert isinstance(allocated, float)
    assert allocated == 5.0
    assert reason == "approved"
