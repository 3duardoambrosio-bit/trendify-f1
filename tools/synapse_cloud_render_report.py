import json, os, argparse
from typing import Any, Dict, List, Optional

def money(x: float, nd: int = 2) -> str:
    return f"{x:,.{nd}f}"

def pct(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}%"

def is_inf(x: Any) -> bool:
    return isinstance(x, float) and (x == float("inf"))

def fmt_inf(x: Any, nd: int = 2) -> str:
    if is_inf(x): return "INF"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)

def compute_path_summary(path: List[Dict[str, Any]]) -> Dict[str, int]:
    first_profit = 0
    first_cum_ge_0 = 0
    profitable_months = 0
    for row in path:
        m = int(row.get("m", 0))
        net = float(row.get("net_mxn", 0.0))
        cum = float(row.get("cum_mxn", 0.0))
        if net >= 0:
            profitable_months += 1
            if first_profit == 0:
                first_profit = m
        if cum >= 0 and first_cum_ge_0 == 0:
            first_cum_ge_0 = m
    return {
        "first_profitable_month": first_profit,
        "first_cum_net_ge_0_month": first_cum_ge_0,
        "profitable_months": profitable_months,
    }

def pick_best_finished(scenarios: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    finished = [s for s in scenarios if str(s.get("label","")).startswith("FINISHED")]
    viable = [s for s in finished if int(s.get("baseline",{}).get("viable",0)) == 1]
    if not viable:
        return None
    viable.sort(
        key=lambda s: (
            float(s["baseline"].get("net_usd_after_target", -1e18)),
            float(s["baseline"].get("headroom_unit", -1e18)),
        ),
        reverse=True,
    )
    return viable[0]

def md_table(rows: List[List[str]]) -> str:
    # rows[0] = header
    if not rows: return ""
    header = rows[0]
    body = rows[1:]
    out = []
    out.append("| " + " | ".join(header) + " |")
    out.append("| " + " | ".join(["---"] * len(header)) + " |")
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out) + "\n"

def render_md(payload: Dict[str, Any]) -> str:
    scenarios = payload.get("scenarios", [])
    version = payload.get("version", "unknown")
    cfg_used = int(payload.get("config_used", 0))

    best = pick_best_finished(scenarios)
    best_label = best.get("label") if best else "NONE"

    # Executive scenario table
    rows = [["label","viable","sev","unit","thr","headroom","net_usd_after_target","ads_req_target"]]
    for s in scenarios:
        b = s.get("baseline", {})
        ads_req = b.get("ads_required_for_target_profit", float("inf"))
        rows.append([
            str(s.get("label","")),
            str(int(b.get("viable",0))),
            str(int(b.get("severity_unit_gap",0))),
            f"{float(b.get('unit',0.0)):.2f}",
            f"{float(b.get('thr',0.0)):.2f}",
            f"{float(b.get('headroom_unit',0.0)):.2f}",
            money(float(b.get("net_usd_after_target",0.0))),
            ("INF" if is_inf(ads_req) else money(float(ads_req))),
        ])

    md = []
    md.append(f"# SYNAPSE Forecast  Claude-Style Report ({version})\n")
    md.append("## Executive Summary\n")
    md.append(f"- Config usada: `{cfg_used}` (0=defaults, 1=json externo)\n")
    md.append(f"- Best finished viable: **{best_label}**\n")

    # Quick flags: current viability
    cur = next((s for s in scenarios if s.get("label") == "CURRENT"), None)
    if cur:
        b = cur.get("baseline", {})
        md.append(f"- CURRENT viable: `{int(b.get('viable',0))}` | unit={float(b.get('unit',0.0)):.2f} vs thr={float(b.get('thr',0.0)):.2f} | net_after_target={money(float(b.get('net_usd_after_target',0.0)))}\n")

    md.append("\n## Scenario Table (Exec)\n")
    md.append(md_table(rows))

    if best:
        b = best.get("baseline", {})
        i = best.get("inputs", {})
        req = best.get("required", {})
        path = best.get("path", [])
        summ = compute_path_summary(path)

        md.append("\n## Winner Detail\n")
        md.append(f"### {best_label}\n")
        md.append(f"- viable: `{int(b.get('viable',0))}` | sev: `{int(b.get('severity_unit_gap',0))}`\n")
        md.append(f"- unit={float(b.get('unit',0.0)):.3f} | thr={float(b.get('thr',0.0)):.3f} | headroom={float(b.get('headroom_unit',0.0)):.3f}\n")
        md.append(f"- net_usd_after_target={money(float(b.get('net_usd_after_target',0.0)))}\n")
        md.append(f"- ads_required_for_target_profit={fmt_inf(b.get('ads_required_for_target_profit', float('inf')))}\n")
        md.append("\n### Inputs\n")
        md.append(md_table([
            ["k","v"],
            ["mxn_per_usd", str(i.get("mxn_per_usd"))],
            ["aov_mxn", str(i.get("aov_mxn"))],
            ["fixed_usd", str(i.get("fixed_usd"))],
            ["ads_usd", str(i.get("ads_usd"))],
            ["roas_paid", str(i.get("roas_paid"))],
            ["ltv", str(i.get("ltv"))],
            ["gm", str(i.get("gm"))],
            ["refund", str(i.get("refund"))],
            ["profit_target_usd", str(i.get("profit_target_usd"))],
        ]))

        md.append("\n### Move ONE lever (Required)\n")
        # Nota: esto te dice cuánto debe ser X manteniendo lo demás constante para llegar al umbral.
        md.append(md_table([
            ["lever","required","notes"],
            ["roas_paid_required", fmt_inf(req.get("roas_paid_required", float("inf")), 3), "manteniendo ltv, gm, refund"],
            ["ltv_mult_required", fmt_inf(req.get("ltv_mult_required", float("inf")), 3), "manteniendo roas, gm, refund"],
            ["gross_margin_required", fmt_inf(req.get("gross_margin_required", float("inf")), 3), "manteniendo roas, ltv, refund"],
            ["ads_min_required", fmt_inf(req.get("ads_min_required", float("inf")), 2), "manteniendo unit; cubre fixed+target"],
        ]))

        md.append("\n### Path Summary\n")
        md.append(f"- first_profitable_month: `{summ['first_profitable_month']}`\n")
        md.append(f"- first_cum_net_ge_0_month: `{summ['first_cum_net_ge_0_month']}`\n")
        md.append(f"- profitable_months: `{summ['profitable_months']}`\n")

        # Compact top 6 path rows + last row
        compact = []
        header = ["m","ads_usd","roas","ltv","gm","ref","unit","thr","net_mxn","cum_mxn"]
        compact.append(header)
        for row in path[:6]:
            compact.append([
                str(row.get("m")),
                str(int(float(row.get("ads_usd",0)))),
                f"{float(row.get('roas',0.0)):.2f}",
                f"{float(row.get('ltv',0.0)):.2f}",
                f"{float(row.get('gm',0.0)):.2f}",
                f"{float(row.get('ref',0.0)):.2f}",
                f"{float(row.get('unit',0.0)):.2f}",
                f"{float(row.get('thr',0.0)):.2f}",
                money(float(row.get("net_mxn",0.0)),0),
                money(float(row.get("cum_mxn",0.0)),0),
            ])
        if len(path) > 6:
            last = path[-1]
            compact.append([
                str(last.get("m")),
                str(int(float(last.get("ads_usd",0)))),
                f"{float(last.get('roas',0.0)):.2f}",
                f"{float(last.get('ltv',0.0)):.2f}",
                f"{float(last.get('gm',0.0)):.2f}",
                f"{float(last.get('ref',0.0)):.2f}",
                f"{float(last.get('unit',0.0)):.2f}",
                f"{float(last.get('thr',0.0)):.2f}",
                money(float(last.get("net_mxn",0.0)),0),
                money(float(last.get("cum_mxn",0.0)),0),
            ])
        md.append("\n### Path (compact)\n")
        md.append(md_table(compact))

    md.append("\n---\n")
    md.append("## Gates (Numeric)\n")
    md.append("REPORT_MD_OK=1\n")
    md.append(f"RULE_scenarios_ge_1={int(len(scenarios) >= 1)}\n")
    md.append(f"RULE_best_finished_label_ne_NONE={int(best_label != 'NONE')}\n")

    return "".join(md)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--injson", default=os.path.join("out","forecast","synapse_report_v13_1.json"))
    ap.add_argument("--outmd", default=os.path.join("out","forecast","synapse_cloud_report.md"))
    args = ap.parse_args()

    with open(args.injson, "r", encoding="utf-8") as f:
        payload = json.load(f)

    md = render_md(payload)

    os.makedirs(os.path.dirname(args.outmd), exist_ok=True)
    with open(args.outmd, "w", encoding="utf-8") as f:
        f.write(md)

    print("RENDER_OK=1")
    print(f"OUT_MD={args.outmd}")
    print(f"RULE_md_written={int(os.path.exists(args.outmd))}")
    print("REPORT_MD_OK=1")

if __name__ == "__main__":
    main()
