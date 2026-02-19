from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

__MARKER__ = "META_AUTOPILOT_2026-01-19_V1"

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
    except Exception:
        return default

def _risk_color(status: str) -> str:
    s = _safe_str(status).upper()
    if s == "OK":
        return "GREEN"
    if s == "WARN":
        return "YELLOW"
    return "RED"

def _txt(out: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("============================================================")
    lines.append("SYNAPSE META AUTOPILOT (RECOMMENDER)")
    lines.append("============================================================")
    lines.append(f"marker: {out.get('marker','-')}")
    lines.append(f"ts: {out.get('ts','-')}")
    lines.append(f"health: {out.get('health','-')}")
    lines.append("")
    lines.append("=== CONTEXT ===")
    ctx = out.get("context") or {}
    lines.append(f"mode: {ctx.get('mode','-')}  report_status: {ctx.get('report_status','-')}  reason: {ctx.get('report_reason','-')}")
    lines.append(f"fp12: {ctx.get('fp12','-')}  files_sha12: {ctx.get('files_sha12','-')}  missing_files: {ctx.get('missing_files',0)}")
    lines.append(f"runs_indexed: {ctx.get('runs_indexed',0)}  last_run_ts: {ctx.get('last_run_ts','-')}")
    lines.append("")
    lines.append("=== NEXT ACTIONS (prioritized) ===")
    actions = out.get("next_actions") or []
    if not actions:
        lines.append("- (none)")
    else:
        for a in actions:
            lines.append(f"- P{a.get('priority',9)} | {a.get('title','-')}")
            lines.append(f"  why: {a.get('why','-')}")
            cmd = a.get("cmd","")
            if cmd:
                lines.append(f"  cmd: {cmd}")
    lines.append("")
    lines.append("============================================================")
    return "\n".join(lines)

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.meta_autopilot", description="Recommend next actions based on latest report + run index. No execution.")
    ap.add_argument("--report", default="data/run/meta_publish_report.json")
    ap.add_argument("--index", default="data/run/meta_publish_runs_index.json")
    ap.add_argument("--out-json", default="data/run/meta_autopilot.json")
    ap.add_argument("--out-txt", default="data/run/meta_autopilot.txt")
    args = ap.parse_args(argv)

    report = _read_json(Path(args.report))
    index = _read_json(Path(args.index))

    report_status = _safe_str(report.get("status","-")).upper()
    report_reason = _safe_str(report.get("reason","-"))
    mode = _safe_str(report.get("mode","simulate")).lower()
    fp12 = _safe_str(report.get("execute_fp12") or report.get("preflight_fp12") or "")
    files = report.get("files") if isinstance(report.get("files"), dict) else {}
    missing_files = _safe_int(files.get("missing", 0), 0)
    files_sha12 = _safe_str(files.get("overall_sha12",""))

    runs = index.get("runs") if isinstance(index.get("runs"), list) else []
    runs_indexed = len(runs)
    last_run_ts = runs[0].get("ts","") if runs else ""

    next_actions: List[Dict[str, Any]] = []

    # 0) reglas duras
    if report_status == "FAIL":
        next_actions.append({
            "priority": 0,
            "title": "Bloqueo: arreglar FAIL antes de seguir",
            "why": f"El reporte marca FAIL por: {report_reason}. Avanzar así es construir sobre arena.",
            "cmd": "python -m synapse.meta_run_report",
        })
    else:
        # 1) higiene de archivos
        if missing_files > 0:
            next_actions.append({
                "priority": 1,
                "title": "Cerrar gap: missing_files = 0",
                "why": "En live esto debe ser FAIL automático. Aunque estés en simulate, es deuda técnica peligrosa.",
                "cmd": "python -m synapse.meta_api_day_meta --mode simulate --status PAUSED --daily-budget 500 --targeting-json @exports/targeting_mx_broad.json --promoted-object-json @exports/promoted_object_purchase.json --page-id 123 --ig-actor-id 123 --pixel-id 123",
            })

        # 2) determinismo (tu superpoder)
        if fp12 and runs_indexed >= 2:
            # si últimas corridas comparten fingerprint, celebramos
            last = [r.get("run_fingerprint_12","") for r in runs[:5]]
            stable = (len(set([x for x in last if x])) == 1) if any(last) else False
            if stable:
                next_actions.append({
                    "priority": 2,
                    "title": "Congelar inputs: pipeline determinista confirmado",
                    "why": "FP12 estable = puedes hacer experimentos sin miedo a drift. Esto es oro operativo.",
                    "cmd": "python -m synapse.meta_history_index",
                })
            else:
                next_actions.append({
                    "priority": 2,
                    "title": "Auditar drift: FP12 cambió entre runs",
                    "why": "Si cambian assets/targeting/promoted_object, cambian fingerprints. Está bien, pero debe ser intencional.",
                    "cmd": "python -m synapse.meta_history_index",
                })

        # 3) preparar autopilot real (sin keys)
        next_actions.append({
            "priority": 3,
            "title": "Preparar Autopilot realista (SIM): loop de ‘recomendar’ sin ejecutar",
            "why": "Siguiente fase: el sistema sugiere acciones (pausar, duplicar, testear) sin tocar Meta. Tú decides.",
            "cmd": "python -m synapse.meta_autopilot",
        })

        # 4) capa de UX: alimentar tu dashboard con series
        next_actions.append({
            "priority": 4,
            "title": "Alimentar dashboard: índice NDJSON para gráficos / trendlines",
            "why": "Tu consola ya traga JSON. NDJSON = fácil graficar runs como negocio (errores, missing_files, fp stability).",
            "cmd": "python -m synapse.meta_history_index",
        })

    health = _risk_color(report_status if report_status in ("OK","WARN","FAIL") else "WARN")

    out = {
        "marker": __MARKER__,
        "ts": report.get("ts",""),
        "health": health,
        "context": {
            "mode": mode,
            "report_status": report_status,
            "report_reason": report_reason,
            "fp12": fp12,
            "files_sha12": files_sha12,
            "missing_files": missing_files,
            "runs_indexed": runs_indexed,
            "last_run_ts": last_run_ts,
        },
        "next_actions": sorted(next_actions, key=lambda a: int(a.get("priority", 9))),
    }

    out_json = Path(args.out_json)
    out_txt = Path(args.out_txt)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    out_txt.write_text(_txt(out), encoding="utf-8")

    cli_print(json.dumps({
        "marker": __MARKER__,
        "status": "OK",
        "out_json": str(out_json.resolve()),
        "out_txt": str(out_txt.resolve()),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())