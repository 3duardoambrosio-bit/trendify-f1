import json
import argparse
from pathlib import Path

def money(x):
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return str(x)

def fnum(x, nd=2):
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)

def extend_plateau(rows, months):
    last = dict(rows[-1])
    net_last = float(last.get("net_mxn", 0.0))
    cum = float(rows[-1].get("cum_mxn", 0.0))
    ext = list(rows)
    m0 = int(last.get("m", len(rows)))
    for m in range(m0 + 1, months + 1):
        r = dict(last)
        r["m"] = m
        cum += net_last
        r["cum_mxn"] = cum
        ext.append(r)
    return ext

def load_scenario(payload, label):
    sc = next((s for s in payload.get("scenarios", []) if s.get("label") == label), None)
    return sc

def month_action(m, unit, thr, net_mxn, cum_mxn, first_profit_m, first_cum0_m):
    # ASCII-only labels (Windows-safe)
    if m < first_profit_m:
        phase = "NEGATIVE_LEARNING"
    elif m == first_profit_m:
        phase = "FIRST_PROFIT"
    else:
        phase = "PROFITABLE"

    if cum_mxn < 0 and m < first_cum0_m:
        runway = "CUM_NEGATIVE"
    elif m == first_cum0_m:
        runway = "CUM_BREAK_EVEN"
    else:
        runway = "CUM_POSITIVE" if cum_mxn >= 0 else "CUM_NEGATIVE"

    gate = "UNIT_LT_THR" if unit < thr else "UNIT_GE_THR"

    # Output actions are deterministic, tied to gates
    actions = []
    if gate == "UNIT_LT_THR":
        actions.append("HOLD_SCALE=1")
        actions.append("FOCUS=ROAS_EFF_AND_MARGIN")
        actions.append("SYSTEM_TASK=INSTRUMENT_FUNNEL_AND_PAYMENT_CHASE")
    else:
        actions.append("HOLD_SCALE=0")
        actions.append("FOCUS=CONTROLLED_SCALE_WITH_GUARDS")
        actions.append("SYSTEM_TASK=AUTOMATE_BUDGET_RAMP_GATES")

    # If still losing money that month, force cost discipline
    if net_mxn < 0:
        actions.append("COST_DISCIPLINE=FIXED_AND_REFUNDS")
    else:
        actions.append("REINVEST_RULE=PARTIAL_REINVEST")

    return phase, runway, gate, actions

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--injson", default="./out/forecast/synapse_report_v13_2.json")
    ap.add_argument("--label", default="FINISHED_BASE")
    ap.add_argument("--months", type=int, default=36)
    args = ap.parse_args()

    p = json.loads(Path(args.injson).read_text(encoding="utf-8"))
    sc = load_scenario(p, args.label)
    if not sc:
        labels = [str(s.get("label")) for s in p.get("scenarios", [])]
        print("SCENARIO_NOT_FOUND=1")
        print("AVAILABLE_LABELS=" + ",".join(labels))
        print("PLAN_OK=0")
        raise SystemExit(2)

    rows = sc.get("path", [])
    if not rows:
        print("PATH_EMPTY=1")
        print("PLAN_OK=0")
        raise SystemExit(3)

    ext = extend_plateau(rows, args.months)

    first_profit = next((r["m"] for r in ext if float(r.get("net_mxn", 0.0)) >= 0.0), 0)
    first_cum0   = next((r["m"] for r in ext if float(r.get("cum_mxn", 0.0)) >= 0.0), 0)

    print(f"LABEL={args.label}")
    print(f"months_rendered={len(ext)}")                    # aceptación: 36
    print(f"first_profitable_month={first_profit}")        # aceptación: >=1
    print(f"first_cum_net_ge_0_month={first_cum0}")        # aceptación: >=1

    print("\n=== MES 01..12 (PLAN + CIFRAS) ===")
    for r in ext[:12]:
        m = int(r["m"])
        unit = float(r.get("unit", 0.0))
        thr  = float(r.get("thr", 0.0))
        net  = float(r.get("net_mxn", 0.0))
        cum  = float(r.get("cum_mxn", 0.0))
        roas = float(r.get("roas", 0.0))
        collect = float(r.get("collect", 1.0))
        roas_eff = roas * collect

        phase, runway, gate, actions = month_action(m, unit, thr, net, cum, first_profit, first_cum0)

        print(f"\nMES={m:02d} phase={phase} runway={runway} gate={gate}")
        print(f"  ads_usd={money(r.get('ads_usd',0))} roas_paid={fnum(roas,2)} collected_rate={fnum(collect,3)} roas_eff_collected={fnum(roas_eff,3)}")
        print(f"  unit={fnum(unit,2)} thr={fnum(thr,2)} net_mxn={money(net)} cum_mxn={money(cum)} orders={int(r.get('orders',0))}")
        for a in actions:
            print(f"  ACTION::{a}")

    # Year summaries (same logic as your timeline tool)
    def sum_range(a, b):
        seg = ext[a-1:b]
        return {
            "ads_usd": sum(float(x.get("ads_usd", 0)) for x in seg),
            "rev_mxn": sum(float(x.get("rev_mxn", 0)) for x in seg),
            "orders":  sum(int(x.get("orders", 0)) for x in seg),
            "net_mxn": sum(float(x.get("net_mxn", 0)) for x in seg),
        }

    y1 = sum_range(1, 12)
    y2 = sum_range(13, 24)
    y3 = sum_range(25, 36)

    print("\n=== ANOS (SUMARIO) ===")
    for idx, y in enumerate([y1, y2, y3], start=1):
        print(f"ANO={idx} ads_usd={money(y['ads_usd'])} rev_mxn={money(y['rev_mxn'])} orders={y['orders']} net_mxn={money(y['net_mxn'])}")

    ok = int(len(ext) == args.months and first_profit > 0 and first_cum0 > 0)
    print("\n=== GATES (NUMERIC) ===")
    print(f"PLAN_OK={ok}")

if __name__ == "__main__":
    main()
