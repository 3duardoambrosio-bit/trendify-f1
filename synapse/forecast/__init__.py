"""
synapse.forecast

Forecast primitives used by tools and future automation.
This package is intentionally small and test-driven.
"""
from .model import (
    MonthRow,
    ForecastScenario,
    ForecastReport,
    parse_month_row,
    extend_plateau,
    first_profitable_month,
    first_cum_net_ge_0_month,
    sum_range,
    load_report,
)

__all__ = [
    "MonthRow",
    "ForecastScenario",
    "ForecastReport",
    "parse_month_row",
    "extend_plateau",
    "first_profitable_month",
    "first_cum_net_ge_0_month",
    "sum_range",
    "load_report",
]
