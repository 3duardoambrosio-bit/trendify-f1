import json, os, argparse
from typing import Any, Dict, List, Optional

def is_inf(x: Any) -> bool:
    try:
        return float(x) == float("inf")
    except Exception:
        return False

def fmt(x: Any, nd: int = 2) -> str:
    if is_inf(x):
        return "INF"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)

def money(x: Any, nd: int = 2) -> str:
    if is_inf(x):
        return "INF"
    try:
        return f"{float(x):,.{nd}f}"
    except Exception:
        return str(x)

def md_table(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:]
    out = []
    out.append("| " + " | ".join(header) + " |")
    out.append("| " + " | ".join(["---"] * len(header)) + " |")
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out) + "\n"

def pick_best_finished(scenarios: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    finished = [s for s in scenarios if str(s.get("label","")).startswith("FINISHED")]
    viable = [s for s in finished if int(s.get("baseline",{}).get("viable",0)) == 1]
    if not viable:
        return None
    viable.sort(
        key=lambda s: (
            float(s.get("baseline", {}).get("net_usd_after_target", -1e18)),
            float(s.get("baseline", {}).get("headroom_unit", -1e18)),
        ),
        reverse=True,
    )
    return viable[0]

def get_baseline_metrics(b: Dict[str, Any]) -> Dict[str, float]:
    # Backward compatible: compute if missing
    collected = float(b.get("collected_rate", 1.0))
    roas_eff = b.get("roas_effective_collected", None)

    if roas_eff is None:
        # Try compute from inputs in baseline if present
        rp = b.get("roas_paid", None)
        if rp is not None:
            roas_eff = float(rp) * float(collected)
        else:
            roas_eff = 0.0
    return {
        "collected_rate": float(collected),
        "roas_effective_collected": float(roas_eff),
    }

def render_md(payload: Dict[str, Any]) -> str:
    scenarios = payload.get("scenarios", [])
    version = payload.get("version", "unknown")
    cfg_used = int(payload.get("config_used", 0))

    best = pick_best_finished(scenarios)
    best_label = best.get("label") if best else "NONE"

    rows = [[
        "label","viable","sev","unit","thr","headroom",
        "net_usd_after_target","collected_rate","roas_effective_collected","ads_req_target"
    ]]

    for s in scenarios:
        b = s.get("baseline", {})
        m = get_baseline_metrics(b)
        ads_req = b.get("ads_required_for_target_profit", float("inf"))
        rows.append([
            str(s.get("label","")),
            str(int(b.get("viable",0))),
            str(int(b.get("severity_unit_gap",0))),
            fmt(b.get("unit",0.0), 2),
            fmt(b.get("thr",0.0), 2),
            fmt(b.get("headroom_unit",0.0), 2),
            money(b.get("net_usd_after_target",0.0), 2),
            fmt(m["collected_rate"], 3),
            fmt(m["roas_effective_collected"], 3),
            ("INF" if is_inf(ads_req) else money(ads_req, 2)),
        ])

    md = []
    md.append(f"# SYNAPSE Forecast Cloud-Style Report ({version})\n\n")
    md.append("## Executive Summary\n\n")
    md.append(f"- config_used: `{cfg_used}`\n")
    md.append(f"- best_finished_viable: **{best_label}**\n\n")

    cur = next((s for s in scenarios if s.get("label") == "CURRENT"), None)
    if cur:
        b = cur.get("baseline", {})
        m = get_baseline_metrics(b)
        md.append(
            "- CURRENT: "
            f"viable=`{int(b.get('viable',0))}` | "
            f"unit={fmt(b.get('unit',0.0),2)} vs thr={fmt(b.get('thr',0.0),2)} | "
            f"collected_rate={fmt(m['collected_rate'],3)} | "
            f"roas_effective_collected={fmt(m['roas_effective_collected'],3)} | "
            f"net_after_target={money(b.get('net_usd_after_target',0.0),2)}\n\n"
        )

    md.append("## Scenario Table (Exec)\n\n")
    md.append(md_table(rows))

    md.append("\n---\n")
    md.append("## Gates (Numeric)\n\n")
    md.append("REPORT_MD_OK=1\n")

    return "".join(md)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--injson", default=os.path.join("out","forecast","synapse_report_v13_2.json"))
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
