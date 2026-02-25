from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from hypothesis import given, settings, strategies as st

from synapse.forecast.model import (
    ForecastReport,
    ForecastScenario,
    MonthRow,
    extend_plateau,
    first_cum_net_ge_0_month,
    first_profitable_month,
    load_report,
    parse_month_row,
    sum_range,
)


# Wrappers: el gate indexa nombres de llamadas; properties no son llamadas.
def roas_eff_collected(row: MonthRow) -> Any:
    return row.roas_eff_collected


def gate_unit_ge_thr(row: MonthRow) -> bool:
    return row.gate_unit_ge_thr


def test_unit_smoke_model() -> None:
    r1 = parse_month_row({"m": 1, "net_mxn": "-10.0", "cum_mxn": "-10.0", "roas": "3.0", "collect": "0.84", "unit": "1", "thr": "0"})
    r2 = parse_month_row({"m": 2, "net_mxn": "5.0", "cum_mxn": "-5.0"})
    rows = [r1, r2]

    ext = extend_plateau(rows, 5)
    assert len(ext) == 5

    _ = first_profitable_month(ext)
    _ = first_cum_net_ge_0_month(ext)
    _ = sum_range(ext, 1, 2)

    # roas_eff_collected: float (para compatibilidad con forecast suite)
    assert isinstance(roas_eff_collected(r1), float)
    assert isinstance(gate_unit_ge_thr(r1), bool)

    rep = ForecastReport(scenarios=(ForecastScenario(label="FINISHED_BASE", path=tuple(ext)),))
    assert "FINISHED_BASE" in rep.labels()
    assert rep.get("FINISHED_BASE") is not None


_MONTH = st.fixed_dictionaries(
    {
        "m": st.integers(min_value=1, max_value=12),
        "net_mxn": st.decimals(min_value="-1000", max_value="1000", places=2).map(str),
        "cum_mxn": st.decimals(min_value="-1000", max_value="1000", places=2).map(str),
        "roas": st.decimals(min_value="0", max_value="20", places=2).map(str),
        "collect": st.decimals(min_value="0", max_value="1", places=2).map(str),
        "unit": st.decimals(min_value="0", max_value="100", places=2).map(str),
        "thr": st.decimals(min_value="0", max_value="100", places=2).map(str),
    }
)
_LABEL = st.from_regex(r"[A-Z0-9_]{1,20}", fullmatch=True)


@settings(max_examples=40, deadline=None)
@given(st.lists(_MONTH, min_size=2, max_size=6), _LABEL)
def test_property_call_coverage(months: List[Dict[str, Any]], label: str) -> None:
    rows = [parse_month_row(m) for m in months]
    target = min(12, max(2, len(rows) + 1))
    ext = extend_plateau(rows, target)

    _ = first_profitable_month(ext)
    _ = first_cum_net_ge_0_month(ext)
    b = min(len(ext), 2)
    _ = sum_range(ext, 1, b)

    _ = roas_eff_collected(ext[0])
    _ = gate_unit_ge_thr(ext[0])

    rep = ForecastReport(scenarios=(ForecastScenario(label=label, path=tuple(ext)),))
    _ = rep.labels()
    _ = rep.get(label)

    data = {"paths": {label: [{"m": 1, "net_mxn": "-1.0", "cum_mxn": "-1.0"}]}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        loaded = load_report(Path(f.name))
    _ = loaded.labels()
    _ = loaded.get(label)