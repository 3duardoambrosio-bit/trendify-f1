from pathlib import Path
import json

from synapse.forecast.model import (
    MonthRow,
    extend_plateau,
    first_profitable_month,
    first_cum_net_ge_0_month,
    load_report,
)

def test_roas_eff_collected_is_deterministic():
    r = MonthRow(m=1, roas=3.0, collect=0.84)
    assert abs(r.roas_eff_collected - 2.52) < 1e-9

def test_extend_plateau_updates_m_and_cum():
    rows = [
        MonthRow(m=1, net_mxn=-10.0, cum_mxn=-10.0),
        MonthRow(m=2, net_mxn=5.0, cum_mxn=-5.0),
    ]
    ext = extend_plateau(rows, 5)
    assert len(ext) == 5
    assert [x.m for x in ext] == [1,2,3,4,5]
    assert ext[2].cum_mxn == 0.0
    assert ext[3].cum_mxn == 5.0
    assert ext[4].cum_mxn == 10.0

def test_first_profit_and_cum_break_even():
    rows = [
        MonthRow(m=1, net_mxn=-1.0, cum_mxn=-1.0),
        MonthRow(m=2, net_mxn=-2.0, cum_mxn=-3.0),
        MonthRow(m=3, net_mxn= 0.0, cum_mxn=-3.0),
        MonthRow(m=4, net_mxn= 5.0, cum_mxn= 2.0),
    ]
    assert first_profitable_month(rows) == 3
    assert first_cum_net_ge_0_month(rows) == 4

def test_load_report_handles_nested_schema_and_alt_keys(tmp_path: Path):
    payload = {
        "meta": {"v": "13.2"},
        "report": {
            "scenarios": [
                {
                    "name": "FINISHED_BASE",
                    "months": [
                        {"month": 1, "net": -10.0, "cum": -10.0},
                        {"month": 2, "net": 5.0, "cum": -5.0},
                    ],
                }
            ]
        },
    }
    p = tmp_path / "r.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    rep = load_report(p)
    sc = rep.get("FINISHED_BASE")
    assert len(sc.path) == 2
    assert sc.path[0].m == 1
    assert sc.path[1].m == 2
    assert sc.path[0].net_mxn == -10.0
    assert sc.path[1].cum_mxn == -5.0

def test_load_report_handles_scenario_map_paths(tmp_path: Path):
    payload = {
        "paths": {
            "FINISHED_BASE": [
                {"m": 1, "net_mxn": -10.0, "cum_mxn": -10.0},
                {"m": 2, "net_mxn": 5.0, "cum_mxn": -5.0},
            ],
            "FINISHED_AGGRESSIVE": [
                {"m": 1, "net_mxn": -20.0, "cum_mxn": -20.0},
            ],
        }
    }
    p = tmp_path / "m.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    rep = load_report(p)
    assert "FINISHED_BASE" in rep.labels()
    assert "FINISHED_AGGRESSIVE" in rep.labels()
    assert rep.get("FINISHED_BASE").path[1].m == 2
