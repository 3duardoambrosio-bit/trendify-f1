from __future__ import annotations

from synapse.infra.cli_logging import cli_print


import argparse
from pathlib import Path

from synapse.infra.diagnostics import find_latest_report, load_report, resolve_diag_dir


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("triage", help="Summarize a crash report (latest or path).")
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--last", action="store_true", help="Use latest report in diag dir.")
    g.add_argument("--path", default=None, help="Path to a specific crash report json.")
    p.add_argument("--dir", default=None, help="Override diagnostics dir (default data/ledger/errors).")
    p.set_defaults(_fn=_run)


def _print_frames(frames: list[dict], limit: int = 8) -> None:
    cli_print("triage: top_frames:", flush=True)
    for fr in frames[-limit:]:
        f = fr.get("file")
        ln = fr.get("line")
        fn = fr.get("func")
        tx = fr.get("text")
        cli_print(f"  - {f}:{ln} in {fn} | {tx}", flush=True)


def _run(args: argparse.Namespace) -> int:
    diag_dir = Path(args.dir) if getattr(args, "dir", None) else resolve_diag_dir()

    path_s = getattr(args, "path", None)
    if path_s:
        p = Path(path_s)
        if not p.exists():
            cli_print(f"triage: ERROR — report not found: {p}", flush=True)
            return 2
        report_path = p
    else:
        report_path = find_latest_report(diag_dir)
        if report_path is None:
            cli_print(f"triage: ERROR — no crash reports found in {diag_dir}", flush=True)
            return 2

    payload = load_report(report_path)

    exc = payload.get("exception") or {}
    et = exc.get("type")
    msg = exc.get("message")

    cli_print(f"triage: report={report_path}", flush=True)
    cli_print(f"triage: fingerprint={payload.get('fingerprint')}", flush=True)
    cli_print(f"triage: exception={et}: {msg}", flush=True)

    hint = payload.get("hint")
    if hint:
        cli_print(f"triage: HINT — {hint}", flush=True)

    ctx = payload.get("context") or {}
    cli = (ctx.get("cli") or {}) if isinstance(ctx, dict) else {}
    if cli:
        cli_print(f"triage: cli.command={cli.get('command')}", flush=True)

    frames = payload.get("frames") or []
    if isinstance(frames, list) and frames:
        _print_frames(frames)

    return 0
