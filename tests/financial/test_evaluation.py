from decimal import Decimal

import pytest

from synapse.financial import (
    Decision,
    FinancialAssumptions,
    FinancialInput,
    FinancialPolicy,
    ScenarioName,
    evaluate_financials,
)


FLAT_DOWNSIDE = FinancialAssumptions(
    downside_price_multiplier=Decimal("1.000"),
    downside_cost_multiplier=Decimal("1.000"),
    downside_cac_multiplier=Decimal("1.000"),
)


def test_pass_healthy_unit_economics_with_explicit_reason_codes():
    result = evaluate_financials(
        FinancialInput(
            product_id="prod-pass",
            name="Healthy Margin Product",
            price=Decimal("999.00"),
            landed_cost=Decimal("260.00"),
            estimated_cac=Decimal("180.00"),
        )
    )

    base = result.scenarios[ScenarioName.BASE]

    assert result.decision == Decision.PASS
    assert base.gross_margin == Decimal("739.00")
    assert base.gross_margin_pct == Decimal("0.7397")
    assert base.estimated_fees == Decimal("41.96")
    assert base.operational_overhead == Decimal("79.92")
    assert base.return_loss_reserve == Decimal("29.97")
    assert base.break_even_cac == Decimal("587.15")
    assert base.contribution_margin == Decimal("407.15")
    assert base.profit_buffer_pct == Decimal("0.4076")
    assert "PASS_HEALTHY_UNIT_ECONOMICS" in result.reason_codes
    assert "PASS_SENSITIVITY_SURVIVES" in result.reason_codes
    assert result.risk_flags == ()


def test_watch_when_product_is_viable_but_below_pass_thresholds():
    result = evaluate_financials(
        FinancialInput(
            product_id="prod-watch",
            name="Borderline Product",
            price=Decimal("600.00"),
            landed_cost=Decimal("260.00"),
            estimated_cac=Decimal("130.00"),
        )
    )

    base = result.scenarios[ScenarioName.BASE]

    assert result.decision == Decision.WATCH
    assert base.gross_margin_pct == Decimal("0.5667")
    assert base.contribution_margin == Decimal("117.60")
    assert "WATCH_HEALTHY_BUT_BELOW_PASS_THRESHOLD" in result.reason_codes


def test_fail_when_margin_is_below_watch_threshold():
    result = evaluate_financials(
        FinancialInput(
            product_id="prod-fail-margin",
            name="Weak Margin Product",
            price=Decimal("500.00"),
            landed_cost=Decimal("290.00"),
            estimated_cac=Decimal("50.00"),
        )
    )

    assert result.decision == Decision.FAIL
    assert "LOW_GROSS_MARGIN_PCT" in result.risk_flags
    assert "FAIL_MARGIN_BELOW_WATCH_THRESHOLD" in result.reason_codes


def test_kill_when_contribution_margin_is_not_positive():
    result = evaluate_financials(
        FinancialInput(
            product_id="prod-kill",
            name="Impossible Economics Product",
            price=Decimal("500.00"),
            landed_cost=Decimal("230.00"),
            estimated_cac=Decimal("250.00"),
        )
    )

    assert result.decision == Decision.KILL
    assert "BASE_CONTRIBUTION_NOT_POSITIVE" in result.risk_flags
    assert "KILL_BASE_UNIT_ECONOMICS" in result.reason_codes


def test_invalid_negative_price_is_rejected():
    with pytest.raises(ValueError, match="price must be positive"):
        evaluate_financials(
            FinancialInput(
                product_id="bad-price",
                name="Bad Price",
                price=Decimal("-1.00"),
                landed_cost=Decimal("10.00"),
                estimated_cac=Decimal("1.00"),
            )
        )


def test_invalid_cost_greater_than_or_equal_to_price_is_rejected():
    with pytest.raises(ValueError, match="landed_cost must be lower than price"):
        evaluate_financials(
            FinancialInput(
                product_id="bad-cost",
                name="Bad Cost",
                price=Decimal("100.00"),
                landed_cost=Decimal("100.00"),
                estimated_cac=Decimal("1.00"),
            )
        )


def test_cac_sensitivity_can_change_decision_to_watch():
    result = evaluate_financials(
        FinancialInput(
            product_id="prod-cac-sensitive",
            name="CAC Sensitive Product",
            price=Decimal("1000.00"),
            landed_cost=Decimal("250.00"),
            estimated_cac=Decimal("510.00"),
        ),
        assumptions=FLAT_DOWNSIDE,
    )

    assert result.decision == Decision.WATCH
    assert result.sensitivity.cac_plus_20_profit < Decimal("0.00")
    assert result.sensitivity.survives_cac_plus_20 is False
    assert "CAC_SENSITIVITY_BREAKS" in result.risk_flags
    assert "WATCH_CAC_PLUS_20_BREAKS" in result.reason_codes


def test_cost_sensitivity_can_change_decision_to_watch():
    policy = FinancialPolicy(
        min_pass_margin_pct=Decimal("0.400"),
        min_watch_margin_pct=Decimal("0.200"),
        min_pass_profit_buffer_pct=Decimal("0.080"),
        min_watch_profit_buffer_pct=Decimal("0.010"),
        min_pass_contribution_margin=Decimal("20.00"),
        min_watch_contribution_margin=Decimal("1.00"),
        max_cac_to_break_even_ratio_pass=Decimal("0.950"),
        max_cac_to_break_even_ratio_watch=Decimal("0.990"),
    )

    result = evaluate_financials(
        FinancialInput(
            product_id="prod-cost-sensitive",
            name="Cost Sensitive Product",
            price=Decimal("1000.00"),
            landed_cost=Decimal("790.00"),
            estimated_cac=Decimal("30.00"),
        ),
        assumptions=FLAT_DOWNSIDE,
        policy=policy,
    )

    assert result.decision == Decision.WATCH
    assert result.sensitivity.cost_plus_10_profit < Decimal("0.00")
    assert result.sensitivity.survives_cost_plus_10 is False
    assert "COST_SENSITIVITY_BREAKS" in result.risk_flags
    assert "WATCH_COST_PLUS_10_BREAKS" in result.reason_codes


def test_price_sensitivity_can_change_decision_to_watch():
    policy = FinancialPolicy(
        min_pass_margin_pct=Decimal("0.400"),
        min_watch_margin_pct=Decimal("0.200"),
        min_pass_profit_buffer_pct=Decimal("0.080"),
        min_watch_profit_buffer_pct=Decimal("0.010"),
        min_pass_contribution_margin=Decimal("20.00"),
        min_watch_contribution_margin=Decimal("1.00"),
        max_cac_to_break_even_ratio_pass=Decimal("0.950"),
        max_cac_to_break_even_ratio_watch=Decimal("0.990"),
    )

    result = evaluate_financials(
        FinancialInput(
            product_id="prod-price-sensitive",
            name="Price Sensitive Product",
            price=Decimal("1000.00"),
            landed_cost=Decimal("780.00"),
            estimated_cac=Decimal("30.00"),
        ),
        assumptions=FLAT_DOWNSIDE,
        policy=policy,
    )

    assert result.decision == Decision.WATCH
    assert result.sensitivity.price_minus_10_profit < Decimal("0.00")
    assert result.sensitivity.survives_price_minus_10 is False
    assert "PRICE_SENSITIVITY_BREAKS" in result.risk_flags
    assert "WATCH_PRICE_MINUS_10_BREAKS" in result.reason_codes


def test_multiple_sensitivity_breaks_are_reported_together():
    policy = FinancialPolicy(
        min_pass_margin_pct=Decimal("0.400"),
        min_watch_margin_pct=Decimal("0.200"),
        min_pass_profit_buffer_pct=Decimal("0.080"),
        min_watch_profit_buffer_pct=Decimal("0.010"),
        min_pass_contribution_margin=Decimal("20.00"),
        min_watch_contribution_margin=Decimal("1.00"),
        max_cac_to_break_even_ratio_pass=Decimal("0.950"),
        max_cac_to_break_even_ratio_watch=Decimal("0.990"),
    )

    result = evaluate_financials(
        FinancialInput(
            product_id="prod-multi-sensitive",
            name="Multi Sensitive Product",
            price=Decimal("1000.00"),
            landed_cost=Decimal("780.00"),
            estimated_cac=Decimal("30.00"),
        ),
        assumptions=FLAT_DOWNSIDE,
        policy=policy,
    )

    assert result.decision == Decision.WATCH
    assert "COST_SENSITIVITY_BREAKS" in result.risk_flags
    assert "PRICE_SENSITIVITY_BREAKS" in result.risk_flags
    assert "WATCH_COST_PLUS_10_BREAKS" in result.reason_codes
    assert "WATCH_PRICE_MINUS_10_BREAKS" in result.reason_codes


def test_output_is_deterministic_for_same_input():
    product = FinancialInput(
        product_id="prod-deterministic",
        name="Deterministic Product",
        price=Decimal("849.00"),
        landed_cost=Decimal("230.00"),
        estimated_cac=Decimal("160.00"),
        expected_units=3,
    )

    result_one = evaluate_financials(product)
    result_two = evaluate_financials(product)

    assert result_one == result_two
    assert result_one.scenarios[ScenarioName.BASE].estimated_profit == Decimal("988.50")


def test_contract_exposes_downside_base_and_upside_scenarios():
    result = evaluate_financials(
        FinancialInput(
            product_id="prod-scenarios",
            name="Scenario Product",
            price=Decimal("999.00"),
            landed_cost=Decimal("260.00"),
            estimated_cac=Decimal("180.00"),
        )
    )

    assert tuple(result.scenarios.keys()) == (
        ScenarioName.DOWNSIDE,
        ScenarioName.BASE,
        ScenarioName.UPSIDE,
    )
    assert result.scenarios[ScenarioName.DOWNSIDE].price == Decimal("899.10")
    assert result.scenarios[ScenarioName.UPSIDE].price == Decimal("1048.95")


def test_engine_has_no_io_or_external_mutation_surface():
    import inspect
    import synapse.financial.evaluation as evaluation

    source = inspect.getsource(evaluation)

    forbidden = (
        "requests.",
        "httpx.",
        "urllib.",
        "subprocess",
        "socket.",
        "open(",
        "Path(",
        "write_text",
        "read_text",
        "os.environ",
    )

    for token in forbidden:
        assert token not in source


def test_policy_validation_rejects_inverted_thresholds():
    with pytest.raises(ValueError, match="min_pass_margin_pct must be >= min_watch_margin_pct"):
        evaluate_financials(
            FinancialInput(
                product_id="bad-policy",
                name="Bad Policy Product",
                price=Decimal("100.00"),
                landed_cost=Decimal("40.00"),
                estimated_cac=Decimal("10.00"),
            ),
            policy=FinancialPolicy(
                min_pass_margin_pct=Decimal("0.300"),
                min_watch_margin_pct=Decimal("0.400"),
            ),
        )