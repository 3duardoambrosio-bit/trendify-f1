"""Deterministic sandbox financial evaluation for product candidates.

This module intentionally performs no IO, no live calls, no external mutation,
and no market scraping. It converts explicit product economics into a typed,
auditable decision that can later be wired into:

    discovery -> financial evaluation -> marketing brief -> decision

The implementation uses Decimal internally to keep money math deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Mapping


_MONEY_QUANT = Decimal("0.01")
_RATIO_QUANT = Decimal("0.0001")


class Decision(str, Enum):
    """Canonical financial decision enum."""

    PASS = "PASS"
    WATCH = "WATCH"
    FAIL = "FAIL"
    KILL = "KILL"


class ScenarioName(str, Enum):
    """Canonical scenario names."""

    DOWNSIDE = "downside"
    BASE = "base"
    UPSIDE = "upside"


@dataclass(frozen=True, slots=True)
class FinancialInput:
    """Product economics supplied by upstream sandbox discovery or operator input."""

    product_id: str
    name: str
    price: Decimal
    landed_cost: Decimal
    estimated_cac: Decimal
    expected_units: int = 1


@dataclass(frozen=True, slots=True)
class FinancialAssumptions:
    """Explicit assumptions used by the financial engine."""

    payment_fee_pct: Decimal = Decimal("0.039")
    payment_fixed_fee: Decimal = Decimal("3.00")
    operational_overhead_pct: Decimal = Decimal("0.080")
    return_loss_pct: Decimal = Decimal("0.030")
    downside_price_multiplier: Decimal = Decimal("0.900")
    downside_cost_multiplier: Decimal = Decimal("1.100")
    downside_cac_multiplier: Decimal = Decimal("1.250")
    upside_price_multiplier: Decimal = Decimal("1.050")
    upside_cost_multiplier: Decimal = Decimal("0.970")
    upside_cac_multiplier: Decimal = Decimal("0.850")


@dataclass(frozen=True, slots=True)
class FinancialPolicy:
    """Thresholds that turn financial metrics into decisions."""

    min_pass_margin_pct: Decimal = Decimal("0.550")
    min_watch_margin_pct: Decimal = Decimal("0.450")
    min_pass_profit_buffer_pct: Decimal = Decimal("0.200")
    min_watch_profit_buffer_pct: Decimal = Decimal("0.080")
    min_pass_contribution_margin: Decimal = Decimal("120.00")
    min_watch_contribution_margin: Decimal = Decimal("50.00")
    kill_contribution_margin: Decimal = Decimal("0.00")
    max_cac_to_break_even_ratio_pass: Decimal = Decimal("0.700")
    max_cac_to_break_even_ratio_watch: Decimal = Decimal("0.900")


DEFAULT_FINANCIAL_POLICY = FinancialPolicy()


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Financial output for one scenario."""

    name: ScenarioName
    price: Decimal
    landed_cost: Decimal
    estimated_cac: Decimal
    estimated_fees: Decimal
    operational_overhead: Decimal
    return_loss_reserve: Decimal
    gross_margin: Decimal
    gross_margin_pct: Decimal
    contribution_margin: Decimal
    break_even_cac: Decimal
    estimated_profit: Decimal
    profit_buffer: Decimal
    profit_buffer_pct: Decimal


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    """Decision-impacting sensitivity checks."""

    cac_plus_20_profit: Decimal
    cost_plus_10_profit: Decimal
    price_minus_10_profit: Decimal
    survives_cac_plus_20: bool
    survives_cost_plus_10: bool
    survives_price_minus_10: bool


@dataclass(frozen=True, slots=True)
class FinancialResult:
    """Complete deterministic financial evaluation result."""

    product_id: str
    name: str
    decision: Decision
    scenarios: Mapping[ScenarioName, ScenarioResult]
    sensitivity: SensitivityResult
    risk_flags: tuple[str, ...]
    reason_codes: tuple[str, ...]
    policy: FinancialPolicy
    assumptions: FinancialAssumptions


def evaluate_financials(
    product: FinancialInput,
    assumptions: FinancialAssumptions | None = None,
    policy: FinancialPolicy = DEFAULT_FINANCIAL_POLICY,
) -> FinancialResult:
    """Evaluate product economics and return a deterministic financial decision."""

    assumptions = assumptions or FinancialAssumptions()
    _validate_product(product)
    _validate_assumptions(assumptions)
    _validate_policy(policy)

    scenarios = {
        ScenarioName.DOWNSIDE: _build_scenario(
            name=ScenarioName.DOWNSIDE,
            product=product,
            assumptions=assumptions,
            price_multiplier=assumptions.downside_price_multiplier,
            cost_multiplier=assumptions.downside_cost_multiplier,
            cac_multiplier=assumptions.downside_cac_multiplier,
        ),
        ScenarioName.BASE: _build_scenario(
            name=ScenarioName.BASE,
            product=product,
            assumptions=assumptions,
            price_multiplier=Decimal("1.000"),
            cost_multiplier=Decimal("1.000"),
            cac_multiplier=Decimal("1.000"),
        ),
        ScenarioName.UPSIDE: _build_scenario(
            name=ScenarioName.UPSIDE,
            product=product,
            assumptions=assumptions,
            price_multiplier=assumptions.upside_price_multiplier,
            cost_multiplier=assumptions.upside_cost_multiplier,
            cac_multiplier=assumptions.upside_cac_multiplier,
        ),
    }

    sensitivity = _build_sensitivity(product=product, assumptions=assumptions)
    decision, risk_flags, reason_codes = _decide(
        scenarios=scenarios,
        sensitivity=sensitivity,
        policy=policy,
    )

    return FinancialResult(
        product_id=product.product_id,
        name=product.name,
        decision=decision,
        scenarios=scenarios,
        sensitivity=sensitivity,
        risk_flags=tuple(sorted(set(risk_flags))),
        reason_codes=tuple(sorted(set(reason_codes))),
        policy=policy,
        assumptions=assumptions,
    )


def _build_scenario(
    *,
    name: ScenarioName,
    product: FinancialInput,
    assumptions: FinancialAssumptions,
    price_multiplier: Decimal,
    cost_multiplier: Decimal,
    cac_multiplier: Decimal,
) -> ScenarioResult:
    price = _money(product.price * price_multiplier)
    landed_cost = _money(product.landed_cost * cost_multiplier)
    estimated_cac = _money(product.estimated_cac * cac_multiplier)

    estimated_fees = _money((price * assumptions.payment_fee_pct) + assumptions.payment_fixed_fee)
    operational_overhead = _money(price * assumptions.operational_overhead_pct)
    return_loss_reserve = _money(price * assumptions.return_loss_pct)

    gross_margin = _money(price - landed_cost)
    gross_margin_pct = _ratio(gross_margin / price)
    break_even_cac = _money(price - landed_cost - estimated_fees - operational_overhead - return_loss_reserve)
    contribution_margin = _money(break_even_cac - estimated_cac)
    estimated_profit = _money(contribution_margin * Decimal(product.expected_units))
    profit_buffer = contribution_margin
    profit_buffer_pct = _ratio(profit_buffer / price)

    return ScenarioResult(
        name=name,
        price=price,
        landed_cost=landed_cost,
        estimated_cac=estimated_cac,
        estimated_fees=estimated_fees,
        operational_overhead=operational_overhead,
        return_loss_reserve=return_loss_reserve,
        gross_margin=gross_margin,
        gross_margin_pct=gross_margin_pct,
        contribution_margin=contribution_margin,
        break_even_cac=break_even_cac,
        estimated_profit=estimated_profit,
        profit_buffer=profit_buffer,
        profit_buffer_pct=profit_buffer_pct,
    )


def _build_sensitivity(
    *,
    product: FinancialInput,
    assumptions: FinancialAssumptions,
) -> SensitivityResult:
    cac_plus_20 = _build_scenario(
        name=ScenarioName.BASE,
        product=product,
        assumptions=assumptions,
        price_multiplier=Decimal("1.000"),
        cost_multiplier=Decimal("1.000"),
        cac_multiplier=Decimal("1.200"),
    )
    cost_plus_10 = _build_scenario(
        name=ScenarioName.BASE,
        product=product,
        assumptions=assumptions,
        price_multiplier=Decimal("1.000"),
        cost_multiplier=Decimal("1.100"),
        cac_multiplier=Decimal("1.000"),
    )
    price_minus_10 = _build_scenario(
        name=ScenarioName.BASE,
        product=product,
        assumptions=assumptions,
        price_multiplier=Decimal("0.900"),
        cost_multiplier=Decimal("1.000"),
        cac_multiplier=Decimal("1.000"),
    )

    return SensitivityResult(
        cac_plus_20_profit=cac_plus_20.estimated_profit,
        cost_plus_10_profit=cost_plus_10.estimated_profit,
        price_minus_10_profit=price_minus_10.estimated_profit,
        survives_cac_plus_20=cac_plus_20.contribution_margin > Decimal("0.00"),
        survives_cost_plus_10=cost_plus_10.contribution_margin > Decimal("0.00"),
        survives_price_minus_10=price_minus_10.contribution_margin > Decimal("0.00"),
    )


def _decide(
    *,
    scenarios: Mapping[ScenarioName, ScenarioResult],
    sensitivity: SensitivityResult,
    policy: FinancialPolicy,
) -> tuple[Decision, list[str], list[str]]:
    base = scenarios[ScenarioName.BASE]
    downside = scenarios[ScenarioName.DOWNSIDE]

    risk_flags: list[str] = []
    reason_codes: list[str] = []

    if base.contribution_margin <= policy.kill_contribution_margin:
        risk_flags.append("BASE_CONTRIBUTION_NOT_POSITIVE")
        reason_codes.append("KILL_BASE_UNIT_ECONOMICS")
        return Decision.KILL, risk_flags, reason_codes

    if base.break_even_cac <= Decimal("0.00"):
        risk_flags.append("BREAK_EVEN_CAC_NOT_POSITIVE")
        reason_codes.append("KILL_NO_PAID_ACQUISITION_ROOM")
        return Decision.KILL, risk_flags, reason_codes

    cac_to_break_even = _ratio(base.estimated_cac / base.break_even_cac)

    if base.gross_margin_pct < policy.min_watch_margin_pct:
        risk_flags.append("LOW_GROSS_MARGIN_PCT")
        reason_codes.append("FAIL_MARGIN_BELOW_WATCH_THRESHOLD")
        return Decision.FAIL, risk_flags, reason_codes

    if base.profit_buffer_pct < policy.min_watch_profit_buffer_pct:
        risk_flags.append("LOW_PROFIT_BUFFER_PCT")
        reason_codes.append("FAIL_BUFFER_BELOW_WATCH_THRESHOLD")
        return Decision.FAIL, risk_flags, reason_codes

    if base.contribution_margin < policy.min_watch_contribution_margin:
        risk_flags.append("LOW_CONTRIBUTION_MARGIN")
        reason_codes.append("FAIL_CONTRIBUTION_BELOW_WATCH_THRESHOLD")
        return Decision.FAIL, risk_flags, reason_codes

    if cac_to_break_even > policy.max_cac_to_break_even_ratio_watch:
        risk_flags.append("CAC_TOO_CLOSE_TO_BREAK_EVEN")
        reason_codes.append("FAIL_CAC_RATIO_ABOVE_WATCH_THRESHOLD")
        return Decision.FAIL, risk_flags, reason_codes

    if downside.contribution_margin <= Decimal("0.00"):
        risk_flags.append("DOWNSIDE_SCENARIO_NEGATIVE")
        reason_codes.append("WATCH_DOWNSIDE_BREAKS")
        return Decision.WATCH, risk_flags, reason_codes

    _append_sensitivity_breaks(
        sensitivity=sensitivity,
        risk_flags=risk_flags,
        reason_codes=reason_codes,
    )

    if risk_flags:
        return Decision.WATCH, risk_flags, reason_codes

    pass_thresholds_met = (
        base.gross_margin_pct >= policy.min_pass_margin_pct
        and base.profit_buffer_pct >= policy.min_pass_profit_buffer_pct
        and base.contribution_margin >= policy.min_pass_contribution_margin
        and cac_to_break_even <= policy.max_cac_to_break_even_ratio_pass
    )

    if pass_thresholds_met:
        reason_codes.append("PASS_HEALTHY_UNIT_ECONOMICS")
        reason_codes.append("PASS_SENSITIVITY_SURVIVES")
        return Decision.PASS, risk_flags, reason_codes

    reason_codes.append("WATCH_HEALTHY_BUT_BELOW_PASS_THRESHOLD")
    return Decision.WATCH, risk_flags, reason_codes


def _append_sensitivity_breaks(
    *,
    sensitivity: SensitivityResult,
    risk_flags: list[str],
    reason_codes: list[str],
) -> None:
    if not sensitivity.survives_cac_plus_20:
        risk_flags.append("CAC_SENSITIVITY_BREAKS")
        reason_codes.append("WATCH_CAC_PLUS_20_BREAKS")

    if not sensitivity.survives_cost_plus_10:
        risk_flags.append("COST_SENSITIVITY_BREAKS")
        reason_codes.append("WATCH_COST_PLUS_10_BREAKS")

    if not sensitivity.survives_price_minus_10:
        risk_flags.append("PRICE_SENSITIVITY_BREAKS")
        reason_codes.append("WATCH_PRICE_MINUS_10_BREAKS")


def _validate_product(product: FinancialInput) -> None:
    if not product.product_id.strip():
        raise ValueError("product_id must not be empty")
    if not product.name.strip():
        raise ValueError("name must not be empty")
    if product.price <= Decimal("0.00"):
        raise ValueError("price must be positive")
    if product.landed_cost <= Decimal("0.00"):
        raise ValueError("landed_cost must be positive")
    if product.estimated_cac < Decimal("0.00"):
        raise ValueError("estimated_cac must be zero or positive")
    if product.landed_cost >= product.price:
        raise ValueError("landed_cost must be lower than price")
    if product.expected_units <= 0:
        raise ValueError("expected_units must be positive")


def _validate_assumptions(assumptions: FinancialAssumptions) -> None:
    ratio_fields = {
        "payment_fee_pct": assumptions.payment_fee_pct,
        "operational_overhead_pct": assumptions.operational_overhead_pct,
        "return_loss_pct": assumptions.return_loss_pct,
    }

    for name, value in ratio_fields.items():
        if value < Decimal("0.00") or value >= Decimal("1.00"):
            raise ValueError(f"{name} must be in range [0, 1)")

    if assumptions.payment_fixed_fee < Decimal("0.00"):
        raise ValueError("payment_fixed_fee must be zero or positive")

    multiplier_fields = {
        "downside_price_multiplier": assumptions.downside_price_multiplier,
        "downside_cost_multiplier": assumptions.downside_cost_multiplier,
        "downside_cac_multiplier": assumptions.downside_cac_multiplier,
        "upside_price_multiplier": assumptions.upside_price_multiplier,
        "upside_cost_multiplier": assumptions.upside_cost_multiplier,
        "upside_cac_multiplier": assumptions.upside_cac_multiplier,
    }

    for name, value in multiplier_fields.items():
        if value <= Decimal("0.00"):
            raise ValueError(f"{name} must be positive")


def _validate_policy(policy: FinancialPolicy) -> None:
    pct_fields = {
        "min_pass_margin_pct": policy.min_pass_margin_pct,
        "min_watch_margin_pct": policy.min_watch_margin_pct,
        "min_pass_profit_buffer_pct": policy.min_pass_profit_buffer_pct,
        "min_watch_profit_buffer_pct": policy.min_watch_profit_buffer_pct,
        "max_cac_to_break_even_ratio_pass": policy.max_cac_to_break_even_ratio_pass,
        "max_cac_to_break_even_ratio_watch": policy.max_cac_to_break_even_ratio_watch,
    }

    for name, value in pct_fields.items():
        if value < Decimal("0.00"):
            raise ValueError(f"{name} must be zero or positive")

    if policy.min_pass_margin_pct < policy.min_watch_margin_pct:
        raise ValueError("min_pass_margin_pct must be >= min_watch_margin_pct")
    if policy.min_pass_profit_buffer_pct < policy.min_watch_profit_buffer_pct:
        raise ValueError("min_pass_profit_buffer_pct must be >= min_watch_profit_buffer_pct")
    if policy.max_cac_to_break_even_ratio_pass > policy.max_cac_to_break_even_ratio_watch:
        raise ValueError("pass CAC ratio must be <= watch CAC ratio")

    money_fields = {
        "min_pass_contribution_margin": policy.min_pass_contribution_margin,
        "min_watch_contribution_margin": policy.min_watch_contribution_margin,
        "kill_contribution_margin": policy.kill_contribution_margin,
    }

    for name, value in money_fields.items():
        if value < Decimal("0.00"):
            raise ValueError(f"{name} must be zero or positive")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANT, rounding=ROUND_HALF_UP)