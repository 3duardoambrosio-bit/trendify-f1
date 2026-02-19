from synapse.forecast.model import (
    MonthRow,
    extend_plateau,
    first_profitable_month,
    first_cum_net_ge_0_month,
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
    # plateau repeats last net_mxn=5.0, cum starts at -5.0
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
