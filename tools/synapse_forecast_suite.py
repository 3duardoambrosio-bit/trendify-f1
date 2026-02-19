import argparse, json, subprocess, sys
from pathlib import Path

# Ensure repo root is on sys.path when running as tools/*.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out

def must_hit(out: str, needle: str) -> int:
    return 1 if needle in out else 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="./out/forecast")
    ap.add_argument("--labels", default="FINISHED_BASE,FINISHED_AGGRESSIVE")
    ap.add_argument("--months", type=int, default=36)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    report_py  = Path("tools") / "synapse_cloud_report_v13_2.py"
    render_py  = Path("tools") / "synapse_cloud_render_report.py"
    plan_py    = Path("tools") / "synapse_forecast_plan.py"

    out_json = outdir / "synapse_report_v13_2.json"
    out_csv  = outdir / "synapse_scenarios_v13_2.csv"
    out_md   = outdir / "synapse_cloud_report.md"
    out_suite= outdir / "synapse_forecast_suite_report.json"

    gates = {}

    # 1) Generate JSON/CSV
    rc1, o1 = run([sys.executable, str(report_py), "--outdir", str(outdir)])
    gates["report_exit_0"] = int(rc1 == 0)
    gates["report_acceptance_ok"] = must_hit(o1, "ACCEPTANCE_OK=1")
    gates["json_exists"] = int(out_json.exists())
    gates["csv_exists"] = int(out_csv.exists())

    # 2) Render MD
    rc2, o2 = run([sys.executable, str(render_py), "--injson", str(out_json), "--outmd", str(out_md)])
    gates["render_exit_0"] = int(rc2 == 0)
    gates["render_report_md_ok"] = must_hit(o2, "REPORT_MD_OK=1")
    gates["md_exists"] = int(out_md.exists())

    # 3) Plan per label
    labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    plans = []
    for lab in labels:
        rc3, o3 = run([sys.executable, str(plan_py), "--injson", str(out_json), "--label", lab, "--months", str(args.months), "--quiet"])
        plan_ok = must_hit(o3, "PLAN_OK=1")
        first_profit = 0
        first_cum0 = 0
        for line in o3.splitlines():
            if line.startswith("first_profitable_month="):
                first_profit = int(line.split("=",1)[1].strip())
            if line.startswith("first_cum_net_ge_0_month="):
                first_cum0 = int(line.split("=",1)[1].strip())
        plans.append({
            "label": lab,
            "exit_0": int(rc3 == 0),
            "plan_ok": int(plan_ok == 1),
            "first_profitable_month": first_profit,
            "first_cum_net_ge_0_month": first_cum0,
        })

    gates["plans_count_ge_1"] = int(len(plans) >= 1)
    gates["plans_all_exit_0"] = int(all(p["exit_0"] == 1 for p in plans))
    gates["plans_all_ok"] = int(all(p["plan_ok"] == 1 for p in plans))
    gates["plans_first_profit_ge_1"] = int(all(p["first_profitable_month"] >= 1 for p in plans))
    gates["plans_first_cum0_ge_1"] = int(all(p["first_cum_net_ge_0_month"] >= 1 for p in plans))

    suite_ok = int(
        gates["report_exit_0"] == 1 and
        gates["report_acceptance_ok"] == 1 and
        gates["json_exists"] == 1 and
        gates["csv_exists"] == 1 and
        gates["render_exit_0"] == 1 and
        gates["render_report_md_ok"] == 1 and
        gates["md_exists"] == 1 and
        gates["plans_count_ge_1"] == 1 and
        gates["plans_all_exit_0"] == 1 and
        gates["plans_all_ok"] == 1 and
        gates["plans_first_profit_ge_1"] == 1 and
        gates["plans_first_cum0_ge_1"] == 1
    )

    payload = {
        "suite_ok": suite_ok,
        "outdir": str(outdir),
        "artifacts": {
            "json": str(out_json),
            "csv": str(out_csv),
            "md": str(out_md),
        },
        "gates": gates,
        "plans": plans,
    }
    out_suite.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== GATES (NUMERIC) ===")
    print(f"SUITE_OK={suite_ok}")
    print(f"RULE_suite_report_written={int(out_suite.exists())}")
    print(f"OUT_SUITE_JSON={out_suite}")

    if suite_ok != 1:
        bad = [(k, v) for k, v in gates.items() if v != 1]
        for k, v in sorted(bad):
            print(f"BAD_GATE {k}={v}")

        # Show what labels report actually contains
        try:
            from synapse.forecast.model import load_report
            if out_json.exists():
                rep = load_report(out_json)
                print("LABELS_AVAILABLE=" + ",".join(rep.labels()))
        except Exception as e:
            print(f"LABELS_AVAILABLE_ERROR={type(e).__name__}")

    return 0 if suite_ok == 1 else 2

if __name__ == "__main__":
    raise SystemExit(main())
