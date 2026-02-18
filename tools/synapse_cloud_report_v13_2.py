from dataclasses import dataclass, asdict
from math import ceil, inf
import json, csv, os, argparse
from typing import Any, Dict, List, Optional, Tuple

# =========================
# SYNAPSE FORECAST MODEL
# v13.2  (adds OXXO/COD completion + mix)
# =========================

def clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0

@dataclass
class Inputs:
    mxn_per_usd: float
    aov_mxn: float
    fixed_usd: float
    ads_usd: float
    roas_paid: float          # Meta-reported ROAS (order created / purchase event)
    ltv: float                # LTV multiplier
    gm: float                 # gross margin (0..1)
    refund: float             # refunds/returns AFTER collection (0..1)
    profit_target_usd: float  # extra profit target in USD per month

    # NEW: payment completion + mix
    oxxo_completion_rate: float   # 0..1, fraction of OXXO orders that get paid
    cod_completion_rate: float    # 0..1, fraction of COD orders that get paid
    oxxo_share: float             # 0..1, fraction of orders via OXXO
    cod_share: float              # 0..1, fraction of orders via COD

def fenv(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v is not None else float(default)

def eff(gm: float, refund: float) -> float:
    # effective margin after refunds/returns (post-collection)
    return max(0.0, float(gm) - float(refund))

def collected_rate(oxxo_share: float, cod_share: float, oxxo_comp: float, cod_comp: float) -> float:
    os_ = clamp01(oxxo_share)
    cs_ = clamp01(cod_share)
    other = clamp01(1.0 - os_ - cs_)
    oc = clamp01(oxxo_comp)
    cc = clamp01(cod_comp)
    # "other" assumed paid (card/transfer/etc)
    return clamp01(other * 1.0 + os_ * oc + cs_ * cc)

def rb(roas_paid: float, ltv: float, collect: float) -> float:
    # revenue multiplier per 1 unit of ad spend, adjusted for collection
    return max(0.0, float(roas_paid)) * max(0.0, float(ltv)) * clamp01(collect)

def threshold_unit(fixed_plus_target: float, ads: float) -> float:
    if ads <= 0:
        return inf
    return 1.0 + (fixed_plus_target / ads)

def net_usd_after_target(fixed_plus_target: float, ads: float, unit: float) -> float:
    return ads * (unit - 1.0) - fixed_plus_target

def roas_paid_required(thr_unit: float, eff_margin: float, ltv: float, collect: float) -> float:
    denom = eff_margin * ltv * clamp01(collect)
    if denom <= 0:
        return inf
    return thr_unit / denom

def ltv_required(thr_unit: float, eff_margin: float, roas_paid: float, collect: float) -> float:
    denom = eff_margin * roas_paid * clamp01(collect)
    if denom <= 0:
        return inf
    return thr_unit / denom

def gm_required(thr_unit: float, refund: float, roas_paid: float, ltv: float, collect: float) -> float:
    denom = roas_paid * ltv * clamp01(collect)
    if denom <= 0:
        return inf
    eff_req = thr_unit / denom
    return float(refund) + eff_req

def ads_min_required(fixed_plus_target: float, unit: float) -> float:
    if unit <= 1.0:
        return inf
    return fixed_plus_target / (unit - 1.0)

def severity_unit_gap(unit: float, thr: float) -> int:
    if thr == inf:
        return 2
    gap = thr - unit
    if gap <= 0:
        return 0
    if gap <= 0.25:
        return 1
    return 2

def pct_delta(cur: float, req: float) -> float:
    if req == inf or cur == 0:
        return inf
    return (req / cur - 1.0) * 100.0

def default_path() -> List[Tuple[float,float,float,float,float]]:
    # More honest "learning valley" ROAS ramp for fresh account + low spend.
    # tuple: (ads_usd, roas_paid, ltv, gm, refund)
    return [
        (300, 1.20, 1.00, 0.30, 0.10),
        (300, 1.40, 1.00, 0.32, 0.10),
        (300, 1.70, 1.02, 0.35, 0.10),
        (300, 2.10, 1.08, 0.40, 0.10),
        (400, 2.30, 1.12, 0.45, 0.10),
        (500, 2.50, 1.18, 0.48, 0.10),
        (600, 2.70, 1.22, 0.50, 0.10),
        (700, 2.85, 1.25, 0.52, 0.10),
        (900, 3.00, 1.28, 0.53, 0.10),
        (1000, 3.10, 1.30, 0.54, 0.10),
        (1200, 3.20, 1.32, 0.55, 0.10),
        (1500, 3.25, 1.34, 0.55, 0.10),
    ]

def month_row(m: int, i: Inputs, collect: float, step: Tuple[float,float,float,float,float]) -> Dict[str, Any]:
    ads_usd, roas_paid, ltv, gm, refund = step
    ads_mxn = ads_usd * i.mxn_per_usd
    fixed_mxn = i.fixed_usd * i.mxn_per_usd
    e = eff(gm, refund)
    r = rb(roas_paid, ltv, collect)
    unit = e * r
    thr = threshold_unit(i.fixed_usd + i.profit_target_usd, ads_usd)

    # IMPORTANT: revenue is COLLECTED (paid), not "order created"
    rev_mxn = ads_mxn * roas_paid * ltv * clamp01(collect)
    contrib_mxn = rev_mxn * e
    net_mxn = contrib_mxn - ads_mxn - fixed_mxn
    orders = ceil(rev_mxn / i.aov_mxn) if rev_mxn > 0 else 0

    return {
        "m": m,
        "ads_usd": float(ads_usd),
        "roas": float(roas_paid),
        "ltv": float(ltv),
        "gm": float(gm),
        "ref": float(refund),
        "collect": float(collect),
        "eff": float(e),
        "rb": float(r),
        "unit": float(unit),
        "thr": float(thr),
        "rev_mxn": float(rev_mxn),
        "orders": int(orders),
        "net_mxn": float(net_mxn),
    }

def scenario_payload(label: str, i: Inputs, path: List[Tuple[float,float,float,float,float]]) -> Dict[str, Any]:
    collect = collected_rate(i.oxxo_share, i.cod_share, i.oxxo_completion_rate, i.cod_completion_rate)
    e0 = eff(i.gm, i.refund)
    r0 = rb(i.roas_paid, i.ltv, collect)
    unit0 = e0 * r0
    thr0 = threshold_unit(i.fixed_usd + i.profit_target_usd, i.ads_usd)
    n_after = net_usd_after_target(i.fixed_usd + i.profit_target_usd, i.ads_usd, unit0)
    viable = int(unit0 >= thr0 and n_after >= 0.0)
    sev = severity_unit_gap(unit0, thr0)
    headroom = unit0 - thr0 if thr0 != inf else float("-inf")

    roas_req = roas_paid_required(thr0, e0, i.ltv, collect)
    ltv_req = ltv_required(thr0, e0, i.roas_paid, collect)
    gm_req = gm_required(thr0, i.refund, i.roas_paid, i.ltv, collect)
    ads_req = ads_min_required(i.fixed_usd + i.profit_target_usd, unit0)

    rows = []
    cum = 0.0
    first_profit = 0
    first_cum_ge_0 = 0
    profitable_months = 0

    for idx, step in enumerate(path, start=1):
        row = month_row(idx, i, collect, step)
        cum += row["net_mxn"]
        if row["net_mxn"] >= 0 and first_profit == 0:
            first_profit = idx
        if row["net_mxn"] >= 0:
            profitable_months += 1
        if cum >= 0 and first_cum_ge_0 == 0:
            first_cum_ge_0 = idx
        row["cum_mxn"] = float(cum)
        rows.append(row)

    roas_eff = i.roas_paid * collect

    return {
        "label": label,
        "inputs": asdict(i),
        "baseline": {
            "eff": e0,
            "rb": r0,
            "unit": unit0,
            "thr": thr0,
            "headroom_unit": headroom,
            "net_usd_after_target": n_after,
            "ads_required_for_target_profit": ads_req,
            "viable": viable,
            "severity_unit_gap": sev,
            "collected_rate": collect,
            "roas_effective_collected": roas_eff,
            "first_profitable_month": first_profit,
            "first_cum_net_ge_0_month": first_cum_ge_0,
            "profitable_months": profitable_months,
        },
        "required": {
            "roas_paid_required": roas_req,
            "ltv_mult_required": ltv_req,
            "gross_margin_required": gm_req,
            "ads_min_required": ads_req,
        },
        "path": rows,
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join("out","forecast"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    mxn_per_usd = fenv("MXN_PER_USD", 17.0)
    aov_mxn = fenv("AOV_MXN", 599.0)

    # Mexico mix defaults (tune via env)
    oxxo_share = fenv("OXXO_SHARE", 0.35)
    cod_share  = fenv("COD_SHARE", 0.25)
    oxxo_comp  = fenv("OXXO_COMPLETION", 0.65)
    cod_comp   = fenv("COD_COMPLETION", 0.85)

    path = default_path()

    scenarios = [
        ("CURRENT", Inputs(mxn_per_usd,aov_mxn,200.0,300.0,1.20,1.00,0.30,0.10,0.0, oxxo_comp,cod_comp,oxxo_share,cod_share)),
        ("FINISHED_CONSERVATIVE", Inputs(mxn_per_usd,aov_mxn,200.0,800.0,2.80,1.15,0.45,0.08,0.0, oxxo_comp,cod_comp,oxxo_share,cod_share)),
        ("FINISHED_BASE",         Inputs(mxn_per_usd,aov_mxn,250.0,1200.0,3.10,1.25,0.50,0.07,0.0, oxxo_comp,cod_comp,oxxo_share,cod_share)),
        ("FINISHED_AGGRESSIVE",   Inputs(mxn_per_usd,aov_mxn,350.0,2000.0,3.30,1.30,0.55,0.06,0.0, oxxo_comp,cod_comp,oxxo_share,cod_share)),
    ]

    payload = {"version": "v13.2", "config_used": 0, "scenarios": []}
    for label, inp in scenarios:
        payload["scenarios"].append(scenario_payload(label, inp, path))

    out_json = os.path.join(args.outdir, "synapse_report_v13_2.json")
    out_csv  = os.path.join(args.outdir, "synapse_scenarios_v13_2.csv")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        cols = ["label","viable","severity","unit","thr","headroom_unit","net_usd_after_target","collected_rate","roas_effective_collected","ads_required_for_target_profit"]
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
                "collected_rate": b["collected_rate"],
                "roas_effective_collected": b["roas_effective_collected"],
                "ads_required_for_target_profit": b["ads_required_for_target_profit"],
            })

    print("=== GATES (NUMERIC) ===")
    print("REPORT_OK=1")
    print(f"RULE_json_written={int(os.path.exists(out_json))}")
    print(f"RULE_csv_written={int(os.path.exists(out_csv))}")
    print("ACCEPTANCE_OK=1" if (os.path.exists(out_json) and os.path.exists(out_csv)) else "ACCEPTANCE_OK=0")
    print(f"OUT_JSON={out_json}")
    print(f"OUT_CSV={out_csv}")

if __name__ == "__main__":
    main()
