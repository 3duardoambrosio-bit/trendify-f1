import argparse, json, subprocess, sys, os
from collections import Counter

def run_gate(csv_path: str, mode: str, allow_placeholders: bool):
    cmd = [sys.executable, "scripts/shopify_contract_gate.py", csv_path, "--mode", mode]
    if allow_placeholders:
        cmd.append("--allow-placeholders")
    subprocess.run(cmd, check=False)
    return f"{csv_path}.contract_report.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--mode", default="demo", choices=["demo","prod"])
    ap.add_argument("--allow-placeholders", action="store_true")
    ap.add_argument("--out", default=None, help="Ruta del reporte limpio (default: <csv>.contract_report.clean.json)")
    args = ap.parse_args()

    report_path = run_gate(args.csv_path, args.mode, args.allow_placeholders)
    if not os.path.exists(report_path):
        print(f"clean_gate: FAIL (no existe report) -> {report_path}", file=sys.stderr)
        return 2

    d = json.load(open(report_path, encoding="utf-8"))
    errors = d.get("errors", [])
    warnings = d.get("warnings", [])

    ignore_types = set()
    if args.allow_placeholders and args.mode == "demo":
        ignore_types.add("image_placeholder_allowed")

    kept = []
    ignored = []
    for w in warnings:
        if isinstance(w, dict) and w.get("type") in ignore_types:
            ignored.append(w)
        else:
            kept.append(w)

    d_clean = dict(d)
    d_clean["warnings"] = kept
    d_clean["warnings_ignored"] = ignored
    d_clean["warnings_ignored_summary"] = dict(Counter(w.get("type","unknown") for w in ignored))

    out_path = args.out or f"{args.csv_path}.contract_report.clean.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d_clean, f, ensure_ascii=False, indent=2)

    print("")
    print("clean_gate: OK")
    print(f"- original_report: {report_path}")
    print(f"- clean_report:    {out_path}")
    print(f"- errors:          {len(errors)}")
    print(f"- warnings_orig:   {len(warnings)}")
    print(f"- warnings_kept:   {len(kept)}")
    print(f"- warnings_ignored:{len(ignored)}  summary={d_clean['warnings_ignored_summary']}")
    return 1 if len(errors) else 0

if __name__ == "__main__":
    raise SystemExit(main())
