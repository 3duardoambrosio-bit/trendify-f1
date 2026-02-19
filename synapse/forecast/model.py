from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json


@dataclass(frozen=True)
class MonthRow:
    """
    Canonical monthly row.

    Goal: be resilient to upstream JSON schema drift.
    We normalize a "month index" + the economics fields we care about.

    Any missing numeric fields default safely.
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


def _pick(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return default


def _looks_like_month_row_dict(x: Any) -> bool:
    return isinstance(x, dict) and any(k in x for k in ["m", "month", "t"])


def _looks_like_path_list(x: Any) -> bool:
    return isinstance(x, list) and len(x) >= 1 and _looks_like_month_row_dict(x[0])


def parse_month_row(d: Dict[str, Any]) -> MonthRow:
    # Month key can drift: m | month | t
    m_raw = _pick(d, ["m", "month", "t"], None)
    if m_raw is None:
        raise ValueError("MISSING_MONTH_KEY: expected one of [m, month, t]")

    return MonthRow(
        m=_as_int(m_raw, "m"),
        ads_usd=_as_float(_pick(d, ["ads_usd", "ads", "spend_usd", "spend", "ad_spend_usd"], 0.0), "ads_usd", 0.0),
        roas=_as_float(_pick(d, ["roas", "paid_roas"], 0.0), "roas", 0.0),
        ltv=_as_float(_pick(d, ["ltv", "ltv_mxn", "ltv_usd"], 1.0), "ltv", 1.0),
        eff=_as_float(_pick(d, ["eff", "efficiency"], 0.0), "eff", 0.0),
        collect=_as_float(_pick(d, ["collect", "collect_rate", "collected_rate"], 1.0), "collect", 1.0),
        unit=_as_float(_pick(d, ["unit", "unit_mxn", "unit_contribution_mxn"], 0.0), "unit", 0.0),
        thr=_as_float(_pick(d, ["thr", "threshold", "unit_threshold_mxn"], 0.0), "thr", 0.0),
        net_mxn=_as_float(_pick(d, ["net_mxn", "net", "net_profit_mxn", "profit_mxn"], 0.0), "net_mxn", 0.0),
        cum_mxn=_as_float(_pick(d, ["cum_mxn", "cum", "cum_net_mxn", "cum_profit_mxn"], 0.0), "cum_mxn", 0.0),
        orders=_as_int(_pick(d, ["orders", "order_count"], 0), "orders"),
        rev_mxn=_as_float(_pick(d, ["rev_mxn", "revenue_mxn", "rev"], 0.0), "rev_mxn", 0.0),
    )


def extend_plateau(rows: List[MonthRow], months: int) -> List[MonthRow]:
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


def _looks_like_scenario_dict(d: Dict[str, Any]) -> bool:
    has_label = any(k in d for k in ["label", "name", "scenario", "id"])
    has_path = any(k in d for k in ["path", "months", "rows", "timeline"])
    return bool(has_label and has_path)


def _extract_path_list_from_value(v: Any) -> Optional[List[Any]]:
    # direct list
    if isinstance(v, list):
        return v
    # dict wrapper containing a list
    if isinstance(v, dict):
        for k in ["path", "months", "rows", "timeline"]:
            vv = v.get(k)
            if isinstance(vv, list):
                return vv
    return None


def _extract_path_list(s: Dict[str, Any]) -> Optional[List[Any]]:
    # direct keys
    for k in ["path", "months", "rows", "timeline"]:
        v = s.get(k)
        vv = _extract_path_list_from_value(v)
        if isinstance(vv, list):
            return vv
    # nested keys
    for nest in ["data", "report", "payload", "result"]:
        v = s.get(nest)
        if isinstance(v, dict):
            for k in ["path", "months", "rows", "timeline"]:
                vv = _extract_path_list_from_value(v.get(k))
                if isinstance(vv, list):
                    return vv
    return None


def _extract_label(s: Dict[str, Any]) -> str:
    return str(_pick(s, ["label", "name", "scenario", "id"], "")).strip()


def _find_scenario_list_anywhere(payload: Any) -> List[Dict[str, Any]]:
    candidates: List[List[Dict[str, Any]]] = []

    def walk(x: Any):
        if isinstance(x, dict):
            if isinstance(x.get("scenarios"), list) and all(isinstance(it, dict) for it in x["scenarios"]):
                candidates.append(x["scenarios"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            if x and all(isinstance(it, dict) for it in x) and any(_looks_like_scenario_dict(it) for it in x):
                candidates.append(x)
            for it in x:
                walk(it)

    walk(payload)
    if not candidates:
        return []

    def score(lst: List[Dict[str, Any]]) -> int:
        sc = 0
        sc += min(len(lst), 50)
        sc += sum(5 for it in lst if any(k in it for k in ["label", "name", "scenario", "id"]))
        sc += sum(5 for it in lst if _extract_path_list(it) is not None)
        for it in lst:
            pl = _extract_path_list(it)
            if isinstance(pl, list) and pl:
                r0 = pl[0]
                if _looks_like_month_row_dict(r0):
                    sc += 10
        return sc

    return sorted(candidates, key=score, reverse=True)[0]


def _scenario_map_from_dict(d: Dict[str, Any]) -> Optional[Dict[str, List[Any]]]:
    """
    Detects a scenario MAP shape like:
      {"FINISHED_BASE": [ {m:1...}, ...], "FINISHED_AGGRESSIVE": [...]}
    or values wrapped:
      {"FINISHED_BASE": {"path":[...]}, ...}
    """
    if not d:
        return None

    hits: Dict[str, List[Any]] = {}
    for k, v in d.items():
        if not isinstance(k, str) or not k.strip():
            continue
        vv = _extract_path_list_from_value(v)
        if isinstance(vv, list) and _looks_like_path_list(vv):
            hits[k.strip()] = vv

    # heuristic: at least 1 scenario found (real-world can be 1+)
    return hits if hits else None


def _find_scenario_map_anywhere(payload: Any) -> Dict[str, List[Any]]:
    candidates: List[Dict[str, List[Any]]] = []

    def walk(x: Any):
        if isinstance(x, dict):
            m = _scenario_map_from_dict(x)
            if m:
                candidates.append(m)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for it in x:
                walk(it)

    walk(payload)
    if not candidates:
        return {}

    def score(m: Dict[str, List[Any]]) -> int:
        sc = 0
        sc += min(len(m), 50)
        # prefer longer paths
        sc += sum(min(len(v), 120) for v in m.values())
        return sc

    return sorted(candidates, key=score, reverse=True)[0]


def load_report(path: Path) -> ForecastReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    # 1) direct known shapes
    scen_list: List[Dict[str, Any]] = []
    scen_map: Dict[str, List[Any]] = {}

    if isinstance(payload, dict):
        if isinstance(payload.get("scenarios"), list):
            scen_list = payload.get("scenarios") or []
        elif isinstance(payload.get("scenarios"), dict):
            scen_map = _scenario_map_from_dict(payload.get("scenarios") or {}) or {}
        elif isinstance(payload.get("paths"), dict):
            scen_map = _scenario_map_from_dict(payload.get("paths") or {}) or {}

    # 2) heuristic fallback
    if not scen_list and not scen_map:
        scen_list = _find_scenario_list_anywhere(payload)

    if not scen_list and not scen_map:
        scen_map = _find_scenario_map_anywhere(payload)

    scenarios: List[ForecastScenario] = []

    # build from list
    for s in scen_list:
        if not isinstance(s, dict):
            continue
        label = _extract_label(s)
        rows_raw = _extract_path_list(s) or []
        if not label:
            continue
        rows: List[MonthRow] = [parse_month_row(r) for r in rows_raw if isinstance(r, dict)]
        scenarios.append(ForecastScenario(label=label, path=rows))

    # build from map
    for label, rows_raw in scen_map.items():
        if not isinstance(rows_raw, list):
            continue
        rows: List[MonthRow] = [parse_month_row(r) for r in rows_raw if isinstance(r, dict)]
        scenarios.append(ForecastScenario(label=label, path=rows))

    return ForecastReport(scenarios=scenarios)
