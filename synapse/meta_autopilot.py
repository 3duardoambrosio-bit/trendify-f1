"""meta_autopilot — Level 4 (NASA Power-of-Ten Grade).

Recommend next actions based on latest report + run index.
Read-only recommender: no execution, no mutation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import deal

from synapse.infra.cli_logging import cli_print

_MARKER = "META_AUTOPILOT_2026-01-19_V1"


# ── Value Objects ─────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class AutopilotConfig:
    """Immutable parsed CLI configuration."""

    report_path: Path
    index_path: Path
    out_json: Path
    out_txt: Path


@dataclass(frozen=True, slots=True)
class ReportContext:
    """Immutable snapshot of report + index state."""

    mode: str
    report_status: str
    report_reason: str
    fp12: str
    files_sha12: str
    missing_files: int
    runs_indexed: int
    last_run_ts: str


@dataclass(frozen=True, slots=True)
class Action:
    """Immutable recommended action."""

    priority: int
    title: str
    why: str
    cmd: str


# ── Private Helpers ───────────────────────────────────────

def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, OSError):
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


def _risk_color(status: str) -> str:
    s = _safe_str(status).upper()
    if s == "OK":
        return "GREEN"
    if s == "WARN":
        return "YELLOW"
    return "RED"


def _parse_autopilot_config(
    argv: Optional[List[str]] = None,
) -> AutopilotConfig:
    ap = argparse.ArgumentParser(prog="synapse.meta_autopilot")
    ap.add_argument("--report", default="data/run/meta_publish_report.json")
    ap.add_argument("--index", default="data/run/meta_publish_runs_index.json")
    ap.add_argument("--out-json", default="data/run/meta_autopilot.json")
    ap.add_argument("--out-txt", default="data/run/meta_autopilot.txt")
    args = ap.parse_args(argv)
    return AutopilotConfig(
        report_path=Path(args.report),
        index_path=Path(args.index),
        out_json=Path(args.out_json),
        out_txt=Path(args.out_txt),
    )


def _build_context(
    report: Dict[str, Any],
    index: Dict[str, Any],
) -> ReportContext:
    files = report.get("files") if isinstance(report.get("files"), dict) else {}
    runs = index.get("runs") if isinstance(index.get("runs"), list) else []
    return ReportContext(
        mode=_safe_str(report.get("mode", "simulate")).lower(),
        report_status=_safe_str(report.get("status", "-")).upper(),
        report_reason=_safe_str(report.get("reason", "-")),
        fp12=_safe_str(
            report.get("execute_fp12")
            or report.get("preflight_fp12")
            or "",
        ),
        files_sha12=_safe_str(files.get("overall_sha12", "")),
        missing_files=_safe_int(files.get("missing", 0)),
        runs_indexed=len(runs),
        last_run_ts=str(runs[0].get("ts", "")) if runs else "",
    )


def _generate_actions_fail(ctx: ReportContext) -> List[Action]:
    return [Action(
        priority=0,
        title="Bloqueo: arreglar FAIL antes de seguir",
        why=f"Reporte marca FAIL: {ctx.report_reason}.",
        cmd="python -m synapse.meta_run_report",
    )]


def _generate_actions_ok(
    ctx: ReportContext,
    index: Dict[str, Any],
) -> List[Action]:
    actions: List[Action] = []

    if ctx.missing_files > 0:
        actions.append(Action(
            priority=1,
            title="Cerrar gap: missing_files = 0",
            why="En live esto seria FAIL automatico.",
            cmd="python -m synapse.meta_api_day_meta --mode simulate",
        ))

    if ctx.fp12 and ctx.runs_indexed >= 2:
        runs = index.get("runs") if isinstance(index.get("runs"), list) else []
        last_fps = [str(r.get("run_fingerprint_12", "")) for r in runs[:5]]
        non_empty = [x for x in last_fps if x]
        stable = len(set(non_empty)) == 1 if non_empty else False
        if stable:
            actions.append(Action(
                priority=2,
                title="Congelar inputs: pipeline determinista confirmado",
                why="FP12 estable = experimentos sin drift.",
                cmd="python -m synapse.meta_history_index",
            ))
        else:
            actions.append(Action(
                priority=2,
                title="Auditar drift: FP12 cambio entre runs",
                why="Debe ser intencional si cambian assets/targeting.",
                cmd="python -m synapse.meta_history_index",
            ))

    actions.append(Action(
        priority=3,
        title="Preparar Autopilot realista (SIM)",
        why="Sistema sugiere acciones sin tocar Meta. Tu decides.",
        cmd="python -m synapse.meta_autopilot",
    ))
    actions.append(Action(
        priority=4,
        title="Alimentar dashboard: indice NDJSON para graficos",
        why="NDJSON = facil graficar runs como negocio.",
        cmd="python -m synapse.meta_history_index",
    ))
    return actions


def _build_output(
    ctx: ReportContext,
    actions: List[Action],
    report: Dict[str, Any],
) -> Dict[str, Any]:
    health = _risk_color(
        ctx.report_status
        if ctx.report_status in ("OK", "WARN", "FAIL")
        else "WARN"
    )
    sorted_actions = sorted(actions, key=lambda a: a.priority)
    return {
        "marker": _MARKER,
        "ts": report.get("ts", ""),
        "health": health,
        "context": asdict(ctx),
        "next_actions": [asdict(a) for a in sorted_actions],
    }


def _format_txt(out: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("SYNAPSE META AUTOPILOT (RECOMMENDER)")
    lines.append("=" * 60)
    lines.append(f"marker: {out.get('marker', '-')}")
    lines.append(f"ts: {out.get('ts', '-')}")
    lines.append(f"health: {out.get('health', '-')}")
    lines.append("")
    ctx = out.get("context") or {}
    lines.append(f"mode: {ctx.get('mode', '-')}  status: {ctx.get('report_status', '-')}")
    lines.append(f"fp12: {ctx.get('fp12', '-')}  missing: {ctx.get('missing_files', 0)}")
    lines.append("")
    lines.append("=== NEXT ACTIONS ===")
    for a in out.get("next_actions") or []:
        lines.append(f"- P{a.get('priority', 9)} | {a.get('title', '-')}")
        cmd = a.get("cmd", "")
        if cmd:
            lines.append(f"  cmd: {cmd}")
    lines.append("=" * 60)
    return "\n".join(lines)


def _persist_output(
    out: Dict[str, Any],
    config: AutopilotConfig,
) -> None:
    config.out_json.parent.mkdir(parents=True, exist_ok=True)
    config.out_json.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    config.out_txt.write_text(_format_txt(out), encoding="utf-8")
    cli_print(json.dumps({
        "marker": _MARKER,
        "status": "OK",
        "out_json": str(config.out_json.resolve()),
        "out_txt": str(config.out_txt.resolve()),
    }, ensure_ascii=False, indent=2, sort_keys=True))


# ── Public Entry Point ────────────────────────────────────

@deal.pre(
    lambda argv=None: argv is None or isinstance(argv, list),
    message="argv must be None or list",
)
@deal.post(
    lambda result: result == 0,
    message="main always returns 0",
)
def main(argv: Optional[List[str]] = None) -> int:
    """Recommend next actions. Read-only, no execution."""
    config = _parse_autopilot_config(argv)
    report = _read_json(config.report_path)
    index = _read_json(config.index_path)
    ctx = _build_context(report, index)

    if ctx.report_status == "FAIL":
        actions = _generate_actions_fail(ctx)
    else:
        actions = _generate_actions_ok(ctx, index)

    out = _build_output(ctx, actions, report)
    _persist_output(out, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
