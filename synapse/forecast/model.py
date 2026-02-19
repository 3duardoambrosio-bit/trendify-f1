from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json


@dataclass(frozen=True)
class MonthRow:
    """
    Canonical monthly row.

    Fields map 1:1 with v13.2 report JSON 'path' rows when present.
    Unknown keys are ignored by parse_month_row.
    """
    m: int
    ads_usd: float = 0.0
    roas: float = 0.0
    ltv: float = 1.0
    eff: float = 0.0
    collect: float = 1.0
    unit: float = 0.0
    thr: float = 0.0
    net_mxn: float = 0.0
    cum_mxn: float = 0.0
    orders: int = 0
    rev_mxn: float = 0.0

    @property
    def roas_eff_collected(self) -> float:
        # paid_roas * collected_rate (realizable)
        return float(self.roas) * float(self.collect)

    @property
    def gate_unit_ge_thr(self) -> bool:
        return float(self.unit) >= float(self.thr)


@dataclass(frozen=True)
class ForecastScenario:
    label: str
    path: List[MonthRow]


@dataclass(frozen=True)
class ForecastReport:
    scenarios: List[ForecastScenario]

    def labels(self) -> List[str]:
        return [s.label for s in self.scenarios]

    def get(self, label: str) -> ForecastScenario:
        sc = next((s for s in self.scenarios if s.label == label), None)
        if sc is None:
            raise KeyError(f"SCENARIO_NOT_FOUND: {label} available={','.join(self.labels())}")
        return sc


def _as_int(v: Any, key: str) -> int:
    try:
        return int(v)
    except Exception as e:
        raise ValueError(f"BAD_INT key={key} value={v!r}") from e


def _as_float(v: Any, key: str, default: float = 0.0) -> float:
    if v is None:
        return float(default)
    try:
        return float(v)
    except Exception as e:
        raise ValueError(f"BAD_FLOAT key={key} value={v!r}") from e


def parse_month_row(d: Dict[str, Any]) -> MonthRow:
    if "m" not in d:
        raise ValueError("MISSING_KEY: m")
    return MonthRow(
        m=_as_int(d.get("m"), "m"),
        ads_usd=_as_float(d.get("ads_usd"), "ads_usd", 0.0),
        roas=_as_float(d.get("roas"), "roas", 0.0),
        ltv=_as_float(d.get("ltv"), "ltv", 1.0),
        eff=_as_float(d.get("eff"), "eff", 0.0),
        collect=_as_float(d.get("collect"), "collect", 1.0),
        unit=_as_float(d.get("unit"), "unit", 0.0),
        thr=_as_float(d.get("thr"), "thr", 0.0),
        net_mxn=_as_float(d.get("net_mxn"), "net_mxn", 0.0),
        cum_mxn=_as_float(d.get("cum_mxn"), "cum_mxn", 0.0),
        orders=_as_int(d.get("orders", 0), "orders"),
        rev_mxn=_as_float(d.get("rev_mxn"), "rev_mxn", 0.0),
    )


def extend_plateau(rows: List[MonthRow], months: int) -> List[MonthRow]:
    """
    Extend a scenario path to N months by repeating the last month economics (plateau),
    updating m and cum_mxn deterministically.
    """
    if months < 1:
        raise ValueError("MONTHS_LT_1")
    if not rows:
        raise ValueError("ROWS_EMPTY")

    ext = list(rows)
    last = ext[-1]
    m0 = int(last.m)
    if m0 >= months:
        return ext[:months]

    net_last = float(last.net_mxn)
    cum = float(last.cum_mxn)

    for m in range(m0 + 1, months + 1):
        cum += net_last
        ext.append(
            MonthRow(
                m=m,
                ads_usd=last.ads_usd,
                roas=last.roas,
                ltv=last.ltv,
                eff=last.eff,
                collect=last.collect,
                unit=last.unit,
                thr=last.thr,
                net_mxn=last.net_mxn,
                cum_mxn=cum,
                orders=last.orders,
                rev_mxn=last.rev_mxn,
            )
        )
    return ext


def first_profitable_month(rows: List[MonthRow]) -> int:
    for r in rows:
        if float(r.net_mxn) >= 0.0:
            return int(r.m)
    return 0


def first_cum_net_ge_0_month(rows: List[MonthRow]) -> int:
    for r in rows:
        if float(r.cum_mxn) >= 0.0:
            return int(r.m)
    return 0


def sum_range(rows: List[MonthRow], a: int, b: int) -> Dict[str, float]:
    if a < 1 or b < a:
        raise ValueError("BAD_RANGE")
    seg = rows[a - 1 : b]
    return {
        "ads_usd": float(sum(r.ads_usd for r in seg)),
        "rev_mxn": float(sum(r.rev_mxn for r in seg)),
        "orders": float(sum(int(r.orders) for r in seg)),
        "net_mxn": float(sum(r.net_mxn for r in seg)),
    }


def load_report(path: Path) -> ForecastReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    scenarios = []
    for s in payload.get("scenarios", []):
        label = str(s.get("label", "")).strip()
        rows_raw = s.get("path", [])
        if not label:
            continue
        rows = [parse_month_row(r) for r in rows_raw]
        scenarios.append(ForecastScenario(label=label, path=rows))
    return ForecastReport(scenarios=scenarios)
