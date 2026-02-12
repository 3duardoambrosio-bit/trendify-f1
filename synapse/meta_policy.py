from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

__MARKER__ = "META_POLICY_2026-01-19_V1"

def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
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
    except Exception:
        return default

@dataclass
class PolicyIssue:
    severity: str  # ERROR|WARN
    code: str
    msg: str
    meta: Dict[str, Any]

def _txt(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("============================================================")
    lines.append("SYNAPSE META POLICY CHECK")
    lines.append("============================================================")
    lines.append(f"marker: {report.get('marker','-')}")
    lines.append(f"mode:   {report.get('mode','-')}")
    lines.append(f"status: {report.get('status','-')}  reason: {report.get('reason','-')}")
    lines.append("")
    lines.append("=== INPUTS ===")
    lines.append(f"report: {report.get('inputs',{}).get('report','-')}")
    lines.append(f"index:  {report.get('inputs',{}).get('index','-')}")
    lines.append("")
    lines.append("=== CHECKS ===")
    for c in report.get("checks", []):
        lines.append(f"- {c.get('name','-')}: {c.get('value')}")
    lines.append("")
    lines.append("=== ISSUES ===")
    issues = report.get("issues") or []
    if not issues:
        lines.append("- (none)")
    else:
        for it in issues[:30]:
            lines.append(f"- {it.get('severity')}/{it.get('code')}: {it.get('msg')}")
    lines.append("============================================================")
    return "\n".join(lines)

def evaluate_policy(*, mode: str, report: Dict[str, Any], index: Dict[str, Any]) -> Dict[str, Any]:
    mode = _safe_str(mode, "simulate").lower()
    issues: List[PolicyIssue] = []
    checks: List[Dict[str, Any]] = []

    rep_status = _safe_str(report.get("status","-")).upper()
    rep_reason = _safe_str(report.get("reason","-"))
    files = report.get("files") if isinstance(report.get("files"), dict) else {}
    missing_files = _safe_int(files.get("missing", 0), 0)

    runs = index.get("runs") if isinstance(index.get("runs"), list) else []
    runs_indexed = len(runs)
    fp12 = _safe_str(report.get("execute_fp12") or report.get("preflight_fp12") or "")

    checks.extend([
        {"name": "report_status", "value": rep_status},
        {"name": "report_reason", "value": rep_reason},
        {"name": "missing_files", "value": missing_files},
        {"name": "runs_indexed", "value": runs_indexed},
        {"name": "fp12", "value": fp12},
    ])

    def warn(code: str, msg: str, meta: Optional[Dict[str, Any]] = None) -> None:
        issues.append(PolicyIssue("WARN", code, msg, meta or {}))

    def err(code: str, msg: str, meta: Optional[Dict[str, Any]] = None) -> None:
        issues.append(PolicyIssue("ERROR", code, msg, meta or {}))

    # baseline: si el report falla, eso siempre es error
    if rep_status == "FAIL":
        err("report_fail", f"meta_run_report está FAIL ({rep_reason}).", {"reason": rep_reason})

    # LIVE rules (hard)
    if mode == "live":
        if missing_files > 0:
            err("missing_files_live", "LIVE bloqueado: faltan archivos referenciados (<FILE:...>).", {"missing": missing_files})

        # no queremos que LIVE arranque ACTIVE por accidente
        # (si el user quiere ACTIVE, que lo pida explícito en CLI)
        # Aquí solo advertimos; el enforce real se hace en api_day flags (más abajo).
        warn("live_safe_default", "Recomendación: en LIVE usar --status PAUSED al primer deploy (evita quemar dinero por accidente).")

        # determinismo mínimo: requiere historial decente
        if runs_indexed < 2:
            warn("low_history", "Poca historia de runs. No es bloqueo, pero dificulta detectar drift.", {"runs_indexed": runs_indexed})

    # SIM rules (soft)
    if mode == "simulate":
        if missing_files > 0:
            warn("missing_files_sim", "SIM ok, pero missing_files es deuda que en LIVE será bloqueo.", {"missing": missing_files})

    # drift signal: últimos 5 fingerprints iguales?
    if runs_indexed >= 2:
        last = [ _safe_str(r.get("run_fingerprint_12","")) for r in runs[:5] ]
        last = [x for x in last if x]
        if last:
            stable = (len(set(last)) == 1)
            checks.append({"name": "fp_stable_last5", "value": stable})
            if mode == "live" and not stable:
                warn("fp_drift", "LIVE: fingerprints recientes no son estables. OK si es intencional, pero ojo drift.", {"last5": last})
        else:
            checks.append({"name": "fp_stable_last5", "value": None})

    status = "OK"
    reason = "clean"
    if any(i.severity == "ERROR" for i in issues):
        status = "FAIL"
        reason = "policy_errors"
    elif issues:
        status = "WARN"
        reason = "policy_warnings"

    return {
        "marker": __MARKER__,
        "mode": mode,
        "status": status,
        "reason": reason,
        "checks": checks,
        "issues": [i.__dict__ for i in issues],
    }

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.meta_policy", description="Policy engine for SIM/LIVE safety rails.")
    ap.add_argument("--mode", default="simulate", choices=["simulate","live"])
    ap.add_argument("--report", default="data/run/meta_publish_report.json")
    ap.add_argument("--index", default="data/run/meta_publish_runs_index.json")
    ap.add_argument("--out-json", default="data/run/meta_policy_check.json")
    ap.add_argument("--out-txt", default="data/run/meta_policy_check.txt")
    args = ap.parse_args(argv)

    report = _read_json(Path(args.report))
    index = _read_json(Path(args.index))

    out = evaluate_policy(mode=args.mode, report=report, index=index)
    out["inputs"] = {
        "report": str(Path(args.report).resolve()),
        "index": str(Path(args.index).resolve()),
    }

    out_json = Path(args.out_json)
    out_txt = Path(args.out_txt)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    out_txt.write_text(_txt(out), encoding="utf-8")

    cli_print(json.dumps({
        "marker": __MARKER__,
        "status": out.get("status","-"),
        "reason": out.get("reason","-"),
        "out_json": str(out_json.resolve()),
        "out_txt": str(out_txt.resolve()),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if out.get("status") != "FAIL" else 2

if __name__ == "__main__":
    raise SystemExit(main())
