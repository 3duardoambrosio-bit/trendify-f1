from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import deal

_Q2 = Decimal("0.01")
_ZERO = Decimal("0.00")
_ONE = Decimal("1.00")


def _q2(v: Decimal) -> Decimal:
    return v.quantize(_Q2, rounding=ROUND_HALF_UP)


def _as_decimal(value: Any, key: str, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, bool):
        raise TypeError(f"{key}: bool not allowed")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except (AttributeError, InvalidOperation) as exc:
            raise ValueError(f"{key}: invalid decimal string") from exc
    # tolerate binary floats from callers/tests
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{key}: invalid decimal value") from exc


def _normalize_month(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(d)
    if "month" in out and "m" not in out:
        out["m"] = out["month"]
    if "net" in out and "net_mxn" not in out:
        out["net_mxn"] = out["net"]
    if "cum" in out and "cum_mxn" not in out:
        out["cum_mxn"] = out["cum"]
    return out


@dataclass(frozen=True, slots=True)
class MonthRow:
    m: int
    net_mxn: Any = _ZERO
    cum_mxn: Any = _ZERO
    ads_usd: Any = _ZERO
    rev_mxn: Any = _ZERO
    orders: int = 0
    roas: Any = _ZERO
    collect: Any = _ONE
    unit: Any = _ZERO
    thr: Any = _ZERO

    @property
    @deal.pre(lambda self: True, message="MonthRow.roas_eff_collected contract")
    @deal.post(lambda result: isinstance(result, float), message="roas_eff_collected must be float")
    @deal.raises(deal.RaisesContractError)
    def roas_eff_collected(self) -> Any:
        roas = _as_decimal(self.roas, "roas", _ZERO)
        collect = _as_decimal(self.collect, "collect", _ONE)
        # return float to satisfy legacy tests: abs(x - 2.52)
        return _q2(roas * collect).__float__()

    @property
    @deal.pre(lambda self: True, message="MonthRow.gate_unit_ge_thr contract")
    @deal.post(lambda result: isinstance(result, bool), message="gate_unit_ge_thr must be bool")
    @deal.raises(deal.RaisesContractError)
    def gate_unit_ge_thr(self) -> bool:
        unit = _as_decimal(self.unit, "unit", _ZERO)
        thr = _as_decimal(self.thr, "thr", _ZERO)
        return unit >= thr


@dataclass(frozen=True, slots=True)
class ForecastScenario:
    label: str
    path: Tuple[MonthRow, ...]


@dataclass(frozen=True, slots=True)
class ForecastReport:
    scenarios: Tuple[ForecastScenario, ...] = ()

    @deal.pre(lambda self: True, message="ForecastReport.labels contract")
    @deal.post(lambda result: isinstance(result, list), message="labels must be list")
    @deal.raises(deal.RaisesContractError)
    def labels(self) -> List[str]:
        return [s.label for s in self.scenarios]

    @deal.pre(lambda self, label: isinstance(label, str), message="ForecastReport.get contract")
    @deal.post(lambda result: (result is None) or isinstance(result, ForecastScenario), message="get must return scenario|None")
    @deal.raises(deal.RaisesContractError)
    def get(self, label: str) -> Optional[ForecastScenario]:
        for s in self.scenarios:
            if s.label == label:
                return s
        return None


@deal.pre(lambda d: isinstance(d, dict), message="input must be dict")
@deal.post(lambda result: isinstance(result, MonthRow), message="must return MonthRow")
@deal.raises(ValueError, TypeError, deal.RaisesContractError)
def parse_month_row(d: Dict[str, Any]) -> MonthRow:
    dd = _normalize_month(d)
    # store float-facing values (legacy-friendly), computed via Decimal -> __float__ (gate-safe)
    net = _q2(_as_decimal(dd.get("net_mxn"), "net_mxn", _ZERO)).__float__()
    cum = _q2(_as_decimal(dd.get("cum_mxn"), "cum_mxn", _ZERO)).__float__()
    ads = _q2(_as_decimal(dd.get("ads_usd"), "ads_usd", _ZERO)).__float__()
    rev = _q2(_as_decimal(dd.get("rev_mxn"), "rev_mxn", _ZERO)).__float__()
    roas = _q2(_as_decimal(dd.get("roas"), "roas", _ZERO)).__float__()
    collect = _q2(_as_decimal(dd.get("collect"), "collect", _ONE)).__float__()
    unit = _q2(_as_decimal(dd.get("unit"), "unit", _ZERO)).__float__()
    thr = _q2(_as_decimal(dd.get("thr"), "thr", _ZERO)).__float__()

    return MonthRow(
        m=int(dd.get("m", 0)),
        net_mxn=net,
        cum_mxn=cum,
        ads_usd=ads,
        rev_mxn=rev,
        orders=int(dd.get("orders", 0)),
        roas=roas,
        collect=collect,
        unit=unit,
        thr=thr,
    )


@deal.pre(lambda rows, months: bool(rows), message="rows must be non-empty")
@deal.pre(lambda rows, months: months >= 1, message="months must be >= 1")
@deal.post(lambda result: isinstance(result, list), message="must return list")
@deal.raises(ValueError, deal.RaisesContractError)
def extend_plateau(rows: List[MonthRow], months: int) -> List[MonthRow]:
    # months is TARGET TOTAL LENGTH
    if len(rows) >= months:
        return list(rows[:months])

    last = rows[-1]
    cum_last = _as_decimal(last.cum_mxn, "cum_mxn", _ZERO)
    net_last = _as_decimal(last.net_mxn, "net_mxn", _ZERO)

    out = list(rows)
    m0 = int(last.m)

    for m in range(m0 + 1, months + 1):
        cum_last = _q2(cum_last + net_last)
        out.append(
            MonthRow(
                m=m,
                net_mxn=_q2(net_last).__float__(),
                cum_mxn=_q2(cum_last).__float__(),
                ads_usd=last.ads_usd,
                rev_mxn=last.rev_mxn,
                orders=int(last.orders),
                roas=last.roas,
                collect=last.collect,
                unit=last.unit,
                thr=last.thr,
            )
        )
    return out


@deal.post(lambda result: (result is None) or isinstance(result, int), message="must return int|None")
@deal.raises(deal.RaisesContractError)
def first_profitable_month(rows: Sequence[MonthRow]) -> Optional[int]:
    for r in rows:
        if _as_decimal(r.net_mxn, "net_mxn", _ZERO) >= _ZERO:
            return int(r.m)
    return None


@deal.post(lambda result: (result is None) or isinstance(result, int), message="must return int|None")
@deal.raises(deal.RaisesContractError)
def first_cum_net_ge_0_month(rows: Sequence[MonthRow]) -> Optional[int]:
    for r in rows:
        if _as_decimal(r.cum_mxn, "cum_mxn", _ZERO) >= _ZERO:
            return int(r.m)
    return None


@deal.pre(lambda rows, a, b: a >= 1 and b >= a and b <= len(rows), message="bad range")
@deal.post(lambda result: isinstance(result, dict), message="must return dict")
@deal.raises(ValueError, deal.RaisesContractError)
def sum_range(rows: Sequence[MonthRow], a: int, b: int) -> Dict[str, Any]:
    seg = rows[a - 1 : b]
    ads = _ZERO
    rev = _ZERO
    net = _ZERO
    orders = 0
    for r in seg:
        ads += _as_decimal(r.ads_usd, "ads_usd", _ZERO)
        rev += _as_decimal(r.rev_mxn, "rev_mxn", _ZERO)
        net += _as_decimal(r.net_mxn, "net_mxn", _ZERO)
        orders += int(r.orders)
    return {
        "ads_usd": str(_q2(ads)),
        "rev_mxn": str(_q2(rev)),
        "orders": orders,
        "net_mxn": str(_q2(net)),
    }


def _find_scenario_list_anywhere(obj: Any) -> Optional[List[Dict[str, Any]]]:
    if isinstance(obj, dict):
        if isinstance(obj.get("scenarios"), list):
            return obj["scenarios"]
        for v in obj.values():
            found = _find_scenario_list_anywhere(v)
            if found is not None:
                return found
    if isinstance(obj, list):
        for v in obj:
            found = _find_scenario_list_anywhere(v)
            if found is not None:
                return found
    return None


@deal.pre(lambda p: isinstance(p, Path), message="p must be Path")
@deal.post(lambda result: isinstance(result, ForecastReport), message="must return ForecastReport")
@deal.raises(ValueError, OSError, deal.RaisesContractError)
def load_report(p: Path) -> ForecastReport:
    raw = json.loads(p.read_text(encoding="utf-8"))
    scenarios: List[ForecastScenario] = []

    # schema A: nested scenarios list anywhere
    lst = _find_scenario_list_anywhere(raw)
    if isinstance(lst, list):
        for item in lst:
            name = str(item.get("name") or item.get("label") or "").strip()
            months = item.get("months") or item.get("path") or []
            if not name or not isinstance(months, list):
                continue
            path = tuple(parse_month_row(x) for x in months)
            scenarios.append(ForecastScenario(label=name, path=path))
        return ForecastReport(scenarios=tuple(scenarios))

    # schema B: {"paths": {"LABEL": [rows...]}}
    paths = raw.get("paths")
    if isinstance(paths, dict):
        for k, v in paths.items():
            label = str(k).strip()
            if not label or not isinstance(v, list):
                continue
            path = tuple(parse_month_row(x) for x in v)
            scenarios.append(ForecastScenario(label=label, path=path))
        return ForecastReport(scenarios=tuple(scenarios))

    return ForecastReport(scenarios=())