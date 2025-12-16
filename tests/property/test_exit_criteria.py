from decimal import Decimal

from hypothesis import given, strategies as st

from ops.exit_criteria_v2 import evaluate_kill_criteria, KillDecision


roas_values = st.floats(
    min_value=0.0,
    max_value=10.0,
    allow_nan=False,
    allow_infinity=False,
)

spend_values = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000"),
    allow_nan=False,
    allow_infinity=False,
)


@given(
    roas=roas_values,
    spend=spend_values,
)
def test_kill_criteria_is_deterministic(roas: float, spend: Decimal) -> None:
    """
    Invariante central:

    evaluate_kill_criteria(roas, spend) debe ser completamente determinista
    (mismo input → misma decisión) y siempre retornar un KillDecision.
    """
    decision1 = evaluate_kill_criteria(roas, spend)
    decision2 = evaluate_kill_criteria(roas, spend)

    assert isinstance(decision1, KillDecision)
    assert isinstance(decision2, KillDecision)
    assert decision1 == decision2
