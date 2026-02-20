from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__MARKER__ = "META_RUN_REPORT_2026-01-19_V1"

def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return {}
    return obj if isinstance(obj, dict) else {}

def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default

def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except (ValueError, TypeError):
        return default

def _pick(*vals: Any, default: Any = "") -> Any:
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str):
            if v.strip():
                return v
        else:
            return v
    return default

def _count_status(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        s = _safe_str(r.get("status", "-")).upper() or "-"
        out[s] = out.get(s, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

def _top_ops(rows: List[Dict[str, Any]], n: int = 8) -> List[Dict[str, Any]]:
    c: Dict[str, int] = {}
    for r in rows:
        op = _safe_str(r.get("op", "-")) or "-"
        c[op] = c.get(op, 0) + 1
    items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [{"op": k, "count": v} for k, v in items]

def _summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    created = 0
    reused = 0
    simulated = 0
    errors = 0
    unresolved_total = 0

    err_samples: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("created_id"):
            created += 1
        if r.get("reused_id") or _safe_str(r.get("status", "")).upper() == "REUSED":
            reused += 1
        if r.get("simulated_id"):
            simulated += 1

        un = r.get("unresolved") or []
        if isinstance(un, list):
            unresolved_total += len(un)

        if r.get("error"):
            errors += 1
            if len(err_samples) < 8:
                err_samples.append({
                    "i": r.get("i"),
                    "key": r.get("key"),
                    "op": r.get("op"),
                    "error": _safe_str(r.get("error"))[:280],
                })

    return {
        "created": created,
        "reused": reused,
        "simulated": simulated,
        "rows": len(rows),
        "rows_with_error": errors,
        "unresolved_placeholders_total": unresolved_total,
        "status_counts": _count_status(rows),
        "top_ops": _top_ops(rows),
        "error_samples": err_samples,
    }

def _txt_report(rep: Dict[str, Any]) -> str:
    # reporte legible tipo "CFO / Ops"
    lines: List[str] = []
    lines.append("============================================================")
    lines.append("SYNAPSE META RUN REPORT (OFFLINE)")
    lines.append("============================================================")
    lines.append(f"marker: {rep.get('marker','-')}")
    lines.append(f"ts: {rep.get('ts','-')}")
    lines.append(f"mode: {rep.get('mode','-')}")
    lines.append(f"status: {rep.get('status','-')}  |  reason: {rep.get('reason','-')}")
    lines.append("")
    lines.append("=== FINGERPRINT CONTRACT ===")
    lines.append(f"preflight_fp12: {rep.get('preflight_fp12','-')}")
    lines.append(f"execute_fp12:   {rep.get('execute_fp12','-')}")
    lines.append(f"fp_match:       {rep.get('fingerprint_match', False)}")
    lines.append("")
    lines.append("=== FILES ===")
    f = rep.get("files") or {}
    lines.append(f"count: {f.get('count',0)}  missing: {f.get('missing',0)}  overall_sha12: {f.get('overall_sha12','-')}")
    lines.append("")
    lines.append("=== EXEC SUMMARY ===")
    s = rep.get("exec") or {}
    lines.append(f"rows: {s.get('rows',0)} | created: {s.get('created',0)} | reused: {s.get('reused',0)} | simulated: {s.get('simulated',0)}")
    lines.append(f"rows_with_error: {s.get('rows_with_error',0)} | unresolved_placeholders_total: {s.get('unresolved_placeholders_total',0)}")
    lines.append("")
    lines.append("=== STATUS COUNTS ===")
    sc = s.get("status_counts") or {}
    if sc:
        for k,v in sc.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("=== TOP OPS ===")
    tops = s.get("top_ops") or []
    if tops:
        for it in tops:
            lines.append(f"- {it.get('op','-')}: {it.get('count',0)}")
    else:
        lines.append("- (none)")
    lines.append("")
    if rep.get("issues"):
        lines.append("=== PREFLIGHT ISSUES (top) ===")
        for it in (rep.get("issues") or [])[:12]:
            lines.append(f"- {it.get('severity','-')}/{it.get('code','-')}: {it.get('msg','')}")
        lines.append("")
    if s.get("error_samples"):
        lines.append("=== ERROR SAMPLES (top) ===")
        for it in s["error_samples"]:
            lines.append(f"- #{it.get('i')} {it.get('key')} {it.get('op')}: {it.get('error')}")
        lines.append("")
    lines.append("============================================================")
    return "\n".join(lines)

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.meta_run_report", description="Offline report for Meta publish runs.")
    ap.add_argument("--plan", default="data/run/meta_publish_plan.json")
    ap.add_argument("--preflight", default="data/run/meta_publish_preflight.json")
    ap.add_argument("--run", default="data/run/meta_publish_run.json")
    ap.add_argument("--secrets-doctor", default="data/run/secrets_doctor.json")
    ap.add_argument("--out-json", default="data/run/meta_publish_report.json")
    ap.add_argument("--out-txt", default="data/run/meta_publish_report.txt")
    args = ap.parse_args(argv)

    plan = _read_json(Path(args.plan))
    pre = _read_json(Path(args.preflight))
    run = _read_json(Path(args.run))
    sd  = _read_json(Path(args.secrets_doctor))

    mode = _safe_str(_pick(run.get("mode"), pre.get("mode"), "simulate")).lower()
    ts = _safe_str(_pick(run.get("ts"), pre.get("ts"), plan.get("ts"), ""))

    fp_pre = _safe_str(pre.get("run_fingerprint_12"))
    fp_run = _safe_str(run.get("run_fingerprint_12"))
    fp_match = bool(fp_pre and fp_run and fp_pre == fp_run)

    files = (run.get("files") or pre.get("files") or {}) if isinstance(run.get("files") or pre.get("files") or {}, dict) else {}
    missing_files = _safe_int(files.get("missing", 0), 0)

    rows = run.get("results") if isinstance(run.get("results"), list) else []
    exec_sum = _summarize_rows(rows)

    issues = pre.get("issues") if isinstance(pre.get("issues"), list) else []

    # status logic (offline): no "live checks" aquí, solo salud operativa
    status = "OK"
    reason = "clean"
    if not fp_match:
        status = "FAIL"
        reason = "fingerprint_mismatch"
    elif exec_sum.get("rows_with_error", 0) > 0:
        status = "FAIL"
        reason = "execute_errors"
    elif mode == "live" and missing_files > 0:
        status = "FAIL"
        reason = "missing_files_live"
    elif missing_files > 0:
        status = "WARN"
        reason = "missing_files"
    elif issues:
        status = "WARN"
        reason = "preflight_issues"

    # secrets doctor summary (safe)
    sd_counts = sd.get("counts") if isinstance(sd.get("counts"), dict) else {}
    sd_summary = {
        "status": _safe_str(sd.get("status","")),
        "missing_required": _safe_int(sd_counts.get("missing_required", 0), 0),
        "present_keys": _safe_int(sd_counts.get("present_keys", 0), 0),
        "scope": _safe_str(sd.get("scope","")),
    }

    report: Dict[str, Any] = {
        "marker": __MARKER__,
        "ts": ts,
        "mode": mode,
        "status": status,
        "reason": reason,
        "fingerprint_match": fp_match,
        "preflight_fp12": fp_pre,
        "execute_fp12": fp_run,
        "files": {
            "count": _safe_int(files.get("count", 0), 0),
            "missing": missing_files,
            "overall_sha12": _safe_str(files.get("overall_sha12","-")),
        },
        "exec": exec_sum,
        "issues": issues[:200],
        "secrets_doctor": sd_summary,
        "inputs": {
            "plan": str(Path(args.plan).resolve()),
            "preflight": str(Path(args.preflight).resolve()),
            "run": str(Path(args.run).resolve()),
            "secrets_doctor": str(Path(args.secrets_doctor).resolve()),
        }
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    out_txt = Path(args.out_txt)
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(_txt_report(report), encoding="utf-8")

    cli_print(json.dumps({
        "marker": __MARKER__,
        "status": status,
        "reason": reason,
        "out_json": str(out_json.resolve()),
        "out_txt": str(out_txt.resolve()),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if status != "FAIL" else 2

if __name__ == "__main__":
    raise SystemExit(main())