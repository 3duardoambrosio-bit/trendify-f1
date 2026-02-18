from dataclasses import dataclass, asdict
from math import ceil, inf
import json, csv, os, argparse

@dataclass
class Inputs:
    mxn_per_usd: float
    aov_mxn: float
    fixed_usd: float
    ads_usd: float
    roas_paid: float
    ltv: float
    gm: float
    refund: float
    profit_target_usd: float

def fenv(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v is not None else float(default)

def eff(gm, refund): return max(0.0, gm - refund)
def rb(roas_paid, ltv): return max(0.0, roas_paid) * max(0.0, ltv)

def threshold_unit(fixed_plus_target, ads):
    if ads <= 0: return inf
    return 1.0 + (fixed_plus_target / ads)

def net_usd(fixed, ads, unit):
    return ads * (unit - 1.0) - fixed

def roas_paid_required(thr_unit, eff_margin, ltv):
    if eff_margin <= 0 or ltv <= 0: return inf
    return thr_unit / (eff_margin * ltv)

def ltv_required(thr_unit, eff_margin, roas_paid):
    if eff_margin <= 0 or roas_paid <= 0: return inf
    return thr_unit / (eff_margin * roas_paid)

def gm_required(thr_unit, refund, roas_paid, ltv):
    denom = roas_paid * ltv
    if denom <= 0: return inf
    eff_req = thr_unit / denom
    return refund + eff_req

def ads_min_required(fixed_plus_target, unit):
    if unit <= 1.0: return inf
    return fixed_plus_target / (unit - 1.0)

def pct_delta(cur, req):
    if req == inf or cur == 0: return inf
    return (req / cur - 1.0) * 100.0

def severity_unit_gap(unit, thr):
    if thr == inf: return 2
    gap = thr - unit
    if gap <= 0: return 0
    if gap <= 0.25: return 1
    return 2

def fmt_inf(x, fmt="{:.2f}"):
    return "INF" if x == inf else fmt.format(x)

def month_row(m, mxn_per_usd, aov_mxn, fixed_usd, ads_usd, roas_paid, ltv, gm, refund, profit_target_usd):
    ads_mxn = ads_usd * mxn_per_usd
    fixed_mxn = fixed_usd * mxn_per_usd

    e = eff(gm, refund)
    r = rb(roas_paid, ltv)
    unit = e * r
    thr = threshold_unit(fixed_usd + profit_target_usd, ads_usd)

    rev_mxn = ads_mxn * roas_paid * ltv
    contrib_mxn = rev_mxn * e
    net_mxn = contrib_mxn - ads_mxn - fixed_mxn
    orders = ceil(rev_mxn / aov_mxn) if rev_mxn > 0 else 0

    return {
        "m": m, "ads_usd": ads_usd, "roas": roas_paid, "ltv": ltv, "gm": gm, "ref": refund,
        "eff": e, "rb": r, "unit": unit, "thr": thr, "rev_mxn": rev_mxn, "orders": orders, "net_mxn": net_mxn
    }

def default_path():
    return [
        (300, 2.50, 1.00, 0.30, 0.10),
        (300, 2.70, 1.00, 0.32, 0.10),
        (300, 3.00, 1.05, 0.40, 0.10),
        (300, 3.50, 1.20, 0.50, 0.10),
        (400, 3.40, 1.22, 0.50, 0.10),
        (500, 3.35, 1.25, 0.52, 0.10),
        (600, 3.30, 1.30, 0.55, 0.10),
        (700, 3.25, 1.30, 0.55, 0.10),
        (900, 3.10, 1.35, 0.55, 0.10),
        (1000,3.05, 1.35, 0.55, 0.10),
        (1200,3.00, 1.40, 0.56, 0.10),
        (1500,2.95, 1.40, 0.56, 0.10),
    ]

def load_config(config_path: str | None):
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f), 1
    if os.path.exists("synapse_scenarios.json"):
        with open("synapse_scenarios.json", "r", encoding="utf-8") as f:
            return json.load(f), 1
    return None, 0

def report(label: str, i: Inputs, path):
    e = eff(i.gm, i.refund)
    r = rb(i.roas_paid, i.ltv)
    unit = e * r
    fixed_plus_target = i.fixed_usd + i.profit_target_usd
    thr = threshold_unit(fixed_plus_target, i.ads_usd)

    n_usd = net_usd(i.fixed_usd, i.ads_usd, unit)
    n_usd_after_target = i.ads_usd * (unit - 1.0) - fixed_plus_target

    viable = int(unit >= thr and n_usd_after_target >= 0.0)
    sev = severity_unit_gap(unit, thr)
    headroom = unit - thr if thr != inf else float("-inf")

    roas_req = roas_paid_required(thr, e, i.ltv)
    ltv_req  = ltv_required(thr, e, i.roas_paid)
    gm_req   = gm_required(thr, i.refund, i.roas_paid, i.ltv)
    ads_req  = ads_min_required(fixed_plus_target, unit)

    rows = []
    cum = 0.0
    first_profit = 0
    first_cum_ge_0 = 0
    profitable_months = 0
    for idx, (ad, rp, ltvx, gmx, rfx) in enumerate(path, start=1):
        row = month_row(idx, i.mxn_per_usd, i.aov_mxn, i.fixed_usd, ad, rp, ltvx, gmx, rfx, i.profit_target_usd)
        cum += row["net_mxn"]
        if row["net_mxn"] >= 0:
            profitable_months += 1
            if first_profit == 0: first_profit = idx
        if cum >= 0 and first_cum_ge_0 == 0: first_cum_ge_0 = idx
        row["cum_mxn"] = cum
        rows.append(row)

    print("======================================================================")
    print(f"SYNAPSE FORECAST  CLOUD STYLE REPORT (v13.1)  ::  {label}")
    print("======================================================================\n")

    print("=== EXEC SUMMARY ===")
    print(f"VIABLE={viable}")
    print(f"SEVERITY_UNIT_GAP={sev}  # 0=GREEN 1=YELLOW 2=RED")
    print(f"unit={unit:.3f}")
    print(f"threshold_unit={thr:.3f}")
    print(f"headroom_unit={headroom:.3f}")
    print(f"net_usd={n_usd:.2f}")
    print(f"net_usd_after_target={n_usd_after_target:.2f}")
    print(f"ads_required_for_target_profit={fmt_inf(ads_req, '{:.2f}')}")
    print(f"first_profitable_month={first_profit}")
    print(f"first_cum_net_ge_0_month={first_cum_ge_0}")
    print(f"profitable_months={profitable_months}\n")

    print("=== INPUTS ===")
    for k, v in asdict(i).items():
        print(f"{k}={v}")
    print("")

    print("=== REQUIRED (move ONE lever) ===")
    print("roas_paid_required=" + ( "INF" if roas_req==inf else f"{roas_req:.3f}") +
          f"  delta_pct={('INF' if roas_req==inf else f'{pct_delta(i.roas_paid, roas_req):.1f}%')}")
    print("ltv_mult_required=" + ( "INF" if ltv_req==inf else f"{ltv_req:.3f}") +
          f"  delta_pct={('INF' if ltv_req==inf else f'{pct_delta(i.ltv, ltv_req):.1f}%')}")
    print("gross_margin_required=" + ( "INF" if gm_req==inf else f"{gm_req:.3f}") +
          f"  delta_pct={('INF' if gm_req==inf else f'{pct_delta(i.gm, gm_req):.1f}%')}")
    print("ads_min_required=" + ( "INF" if ads_req==inf else f"{ads_req:.2f}"))
    print("")

    print("=== 12-STEP PATH (MXN) ===")
    print("M AdsUSD ROAS LTV GM REF Eff RB Unit Thr RevMXN Orders NetMXN CumMXN")
    for row in rows:
        print(f"{row['m']:>2} {row['ads_usd']:>6.0f} {row['roas']:>4.2f} {row['ltv']:>3.2f} "
              f"{row['gm']:>4.2f} {row['ref']:>4.2f} {row['eff']:>4.2f} {row['rb']:>4.2f} "
              f"{row['unit']:>4.2f} {row['thr']:>4.2f} "
              f"{row['rev_mxn']:>7.0f} {row['orders']:>6} {row['net_mxn']:>7.0f} {row['cum_mxn']:>7.0f}")
    print("")

    return {
        "label": label,
        "inputs": asdict(i),
        "baseline": {
            "eff": e, "rb": r, "unit": unit, "thr": thr, "headroom_unit": headroom,
            "net_usd": n_usd, "net_usd_after_target": n_usd_after_target,
            "ads_required_for_target_profit": ads_req,
            "viable": viable, "severity_unit_gap": sev,
        },
        "required": {
            "roas_paid_required": roas_req,
            "ltv_mult_required": ltv_req,
            "gross_margin_required": gm_req,
            "ads_min_required": ads_req,
        },
        "path": rows
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    cfg, cfg_used = load_config(args.config)

    mxn_per_usd = fenv("MXN_PER_USD", 17.0)
    aov_mxn = fenv("AOV_MXN", 599.0)
    path = default_path()
    scenarios = []

    if cfg_used == 1:
        mxn_per_usd = float(cfg.get("mxn_per_usd", mxn_per_usd))
        aov_mxn = float(cfg.get("aov_mxn", aov_mxn))
        path = cfg.get("path", path)
        for s in cfg.get("scenarios", []):
            scenarios.append((
                s["label"],
                Inputs(
                    mxn_per_usd=mxn_per_usd, aov_mxn=aov_mxn,
                    fixed_usd=float(s["fixed_usd"]),
                    ads_usd=float(s["ads_usd"]),
                    roas_paid=float(s["roas_paid"]),
                    ltv=float(s["ltv"]),
                    gm=float(s["gm"]),
                    refund=float(s["refund"]),
                    profit_target_usd=float(s.get("profit_target_usd", 0.0)),
                )
            ))
    else:
        current = Inputs(mxn_per_usd,aov_mxn,fenv("FIXED_USD",200.0),fenv("ADS_USD",300.0),fenv("ROAS_PAID",2.5),
                         fenv("LTV_MULT",1.0),fenv("GROSS_MARGIN",0.30),fenv("REFUND_RATE",0.10),fenv("PROFIT_TARGET_USD",0.0))
        scenarios = [
            ("CURRENT", current),
            ("FINISHED_CONSERVATIVE", Inputs(mxn_per_usd,aov_mxn,200.0,800.0,3.00,1.20,0.45,0.08,0.0)),
            ("FINISHED_BASE",         Inputs(mxn_per_usd,aov_mxn,250.0,1200.0,3.20,1.30,0.50,0.07,0.0)),
            ("FINISHED_AGGRESSIVE",   Inputs(mxn_per_usd,aov_mxn,350.0,2000.0,3.40,1.35,0.55,0.06,0.0)),
        ]

    payload = {"version": "v13.1", "config_used": cfg_used, "scenarios": []}
    for label, inp in scenarios:
        payload["scenarios"].append(report(label, inp, path))

    print("======================================================================")
    print("SCENARIO TABLE (EXEC)")
    print("======================================================================")
    print("label viable sev unit thr headroom net_usd_after_target ads_req_target")
    for s in payload["scenarios"]:
        b = s["baseline"]
        ads_req = b["ads_required_for_target_profit"]
        ads_req_s = "INF" if ads_req == inf else f"{ads_req:.2f}"
        print(f"{s['label']:>22} {b['viable']:>6} {b['severity_unit_gap']:>3} "
              f"{b['unit']:>5.2f} {b['thr']:>5.2f} {b['headroom_unit']:>7.2f} "
              f"{b['net_usd_after_target']:>10.2f} {ads_req_s:>12}")
    print("")

    out_json = os.path.join(args.outdir, "synapse_report_v13_1.json")
    out_csv  = os.path.join(args.outdir, "synapse_scenarios_v13_1.csv")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        cols = ["label","viable","severity","unit","thr","headroom_unit","net_usd_after_target","ads_required_for_target_profit"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in payload["scenarios"]:
            b = s["baseline"]
            w.writerow({
                "label": s["label"],
                "viable": b["viable"],
                "severity": b["severity_unit_gap"],
                "unit": b["unit"],
                "thr": b["thr"],
                "headroom_unit": b["headroom_unit"],
                "net_usd_after_target": b["net_usd_after_target"],
                "ads_required_for_target_profit": b["ads_required_for_target_profit"],
            })

    finished = [s for s in payload["scenarios"] if s["label"].startswith("FINISHED")]
    finished_viable = [s for s in finished if s["baseline"]["viable"] == 1]
    finished_viable_count = len(finished_viable)
    best_label = "NONE"
    if finished_viable_count > 0:
        finished_viable.sort(key=lambda s: (s["baseline"]["net_usd_after_target"], s["baseline"]["headroom_unit"]), reverse=True)
        best_label = finished_viable[0]["label"]

    print("=== GATES (NUMERIC) ===")
    print("REPORT_OK=1")
    print(f"RULE_scenarios_ge_1={int(len(payload['scenarios'])>=1)}")
    print(f"RULE_finished_viable_ge_1={int(finished_viable_count>=1)}")
    print(f"finished_viable_count={finished_viable_count}")
    print(f"best_finished_label={best_label}")
    print(f"RULE_json_written={int(os.path.exists(out_json))}")
    print(f"RULE_csv_written={int(os.path.exists(out_csv))}")
    ok = (len(payload["scenarios"])>=1 and os.path.exists(out_json) and os.path.exists(out_csv))
    print("ACCEPTANCE_OK=1" if ok else "ACCEPTANCE_OK=0")

if __name__ == "__main__":
    main()
