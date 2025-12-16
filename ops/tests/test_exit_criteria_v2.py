from decimal import Decimal

from ops.exit_criteria_v2 import (
    evaluate_kill_criteria,
    KillDecision,
    MIN_SPEND_FOR_DECISION,
    HARD_KILL_ROAS,
    SOFT_KILL_ROAS,
)


def test_insufficient_data_continues() -> None:
    """
    Si el spend está por debajo del mínimo, NUNCA matamos.
    """
    spend = MIN_SPEND_FOR_DECISION - Decimal("0.01")
    decision = evaluate_kill_criteria(roas=0.2, spend=spend)

    assert isinstance(decision, KillDecision)
    assert decision.action == "continue"
    assert decision.reason == "insufficient_data"


def test_hard_kill_when_roas_is_very_low() -> None:
    """
    Con suficiente spend y ROAS por debajo del hard threshold, se mata.
    """
    spend = MIN_SPEND_FOR_DECISION + Decimal("1")
    roas = float(HARD_KILL_ROAS) - 0.1

    decision = evaluate_kill_criteria(roas=roas, spend=spend)

    assert decision.action == "kill"
    assert decision.reason == "roas_below_hard_threshold"


def test_pause_when_roas_between_hard_and_soft() -> None:
    """
    En la franja entre hard y soft threshold, se hace 'pause'.
    """
    spend = MIN_SPEND_FOR_DECISION + Decimal("5")
    roas = (float(HARD_KILL_ROAS) + float(SOFT_KILL_ROAS)) / 2.0

    decision = evaluate_kill_criteria(roas=roas, spend=spend)

    assert decision.action == "pause"
    assert decision.reason == "roas_between_hard_and_soft_threshold"


def test_continue_when_roas_is_good() -> None:
    """
    Si el ROAS es mayor o igual al soft threshold, se sigue corriendo.
    """
    spend = MIN_SPEND_FOR_DECISION + Decimal("5")
    roas = float(SOFT_KILL_ROAS) + 0.2

    decision = evaluate_kill_criteria(roas=roas, spend=spend)

    assert decision.action == "continue"
    assert decision.reason == "roas_acceptable"
