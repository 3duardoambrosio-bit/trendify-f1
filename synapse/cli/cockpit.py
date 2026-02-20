"""Cockpit status CLI: health/tests/flags/budget/safety/last-ledger/all.

Usage:
    python -m synapse.cli.cockpit <subcommand> [--json|--pretty] [--timeout-s N] [--ledger-path PATH]

Default output is JSON (single line, parseable by scripts).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXIT_OK = 0
_EXIT_DEGRADED = 2
_EXIT_ERROR = 3

_ANSI_GREEN = "\033[32m"
_ANSI_YELLOW = "\033[33m"
_ANSI_RED = "\033[31m"
_ANSI_RESET = "\033[0m"
_ANSI_BOLD = "\033[1m"


def _ts_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head_short() -> str | None:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if p.returncode == 0:
            return p.stdout.strip()
    except Exception:
        pass
    return None


def _run_subprocess(
    cmd: list[str], timeout_s: int = 120,
) -> Dict[str, Any]:
    t0 = time.monotonic()
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        stdout_lines = p.stdout.splitlines()
        stderr_lines = p.stderr.splitlines()
        return {
            "returncode": p.returncode,
            "stdout_tail": "\n".join(stdout_lines[-40:]),
            "stderr_tail": "\n".join(stderr_lines[-40:]),
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "returncode": -1,
            "stdout_tail": "",
            "stderr_tail": "timeout after {}s".format(timeout_s),
            "duration_ms": duration_ms,
        }
    except (ValueError, TypeError) as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "returncode": -1,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "duration_ms": duration_ms,
        }


def _base_envelope(mode: str) -> Dict[str, Any]:
    head = _git_head_short()
    envelope: Dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "ts_utc": _ts_utc(),
        "meta": {
            "head_short": head,
            "cwd": str(Path(".").resolve()),
            "python": sys.executable,
        },
        "checks": {},
        "errors": [],
    }
    if head is None:
        envelope["errors"].append({
            "code": "git_unavailable",
            "message": "could not resolve git HEAD",
            "detail": None,
        })
    return envelope


def _print_json(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, default=str))


def _print_pretty(obj: Dict[str, Any]) -> None:
    ok = obj.get("ok", False)
    errors = obj.get("errors", [])
    if not ok:
        color = _ANSI_RED
        label = "RED"
    elif errors:
        color = _ANSI_YELLOW
        label = "YELLOW"
    else:
        color = _ANSI_GREEN
        label = "GREEN"

    summary = obj.get("checks", {}).get("summary", {})
    if summary.get("overall"):
        label = summary["overall"]
        color = {
            "GREEN": _ANSI_GREEN,
            "YELLOW": _ANSI_YELLOW,
            "RED": _ANSI_RED,
        }.get(label, _ANSI_RESET)

    print(f"{_ANSI_BOLD}COCKPIT [{obj.get('mode', '?')}]{_ANSI_RESET}  "
          f"{color}{label}{_ANSI_RESET}  "
          f"ts={obj.get('ts_utc', '?')}")
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _compute_exit(envelope: Dict[str, Any]) -> int:
    if not envelope["ok"]:
        return _EXIT_ERROR
    if envelope["errors"]:
        return _EXIT_DEGRADED
    return _EXIT_OK


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _cmd_health(envelope: Dict[str, Any]) -> None:
    try:
        from synapse.infra.healthcheck import run_checks
        result = run_checks()
        envelope["checks"]["healthcheck"] = result
        if not result.get("ok", True):
            envelope["ok"] = False
    except Exception as exc:
        envelope["ok"] = False
        envelope["errors"].append({
            "code": "healthcheck_import_error",
            "message": "failed to import/run healthcheck",
            "detail": str(exc),
        })


def _cmd_flags(envelope: Dict[str, Any]) -> None:
    try:
        from synapse.infra.feature_flags import FeatureFlags
        flags = FeatureFlags.load()
        envelope["checks"]["flags"] = {
            "count": len(flags.values),
            "values": dict(flags.values),
            "prefix": "SYNAPSE_FLAG_",
        }
    except Exception as exc:
        envelope["ok"] = False
        envelope["errors"].append({
            "code": "flags_load_error",
            "message": "failed to load feature flags",
            "detail": str(exc),
        })


def _cmd_tests(envelope: Dict[str, Any], timeout_s: int = 900) -> None:
    result = _run_subprocess(
        [sys.executable, "-m", "pytest", "-q"],
        timeout_s=timeout_s,
    )
    envelope["checks"]["tests"] = {"pytest": result}
    if result["returncode"] == -1:
        envelope["ok"] = False
        envelope["errors"].append({
            "code": "pytest_failed_to_run",
            "message": "pytest could not be invoked",
            "detail": result["stderr_tail"],
        })
    elif result["returncode"] != 0:
        envelope["ok"] = False
        envelope["errors"].append({
            "code": "pytest_failed",
            "message": "pytest returned non-zero exit code",
            "detail": f"returncode={result['returncode']}",
        })


def _cmd_last_ledger(
    envelope: Dict[str, Any], ledger_path: str | None = None,
) -> None:
    if ledger_path is None:
        ledger_path = os.environ.get(
            "SYNAPSE_LEDGER_PATH", "data/ledger/ledger.ndjson",
        )
    p = Path(ledger_path)
    if not p.exists():
        envelope["checks"]["ledger"] = {"available": False, "path": str(p)}
        envelope["errors"].append({
            "code": "ledger_missing",
            "message": "ledger file not found",
            "detail": str(p),
        })
        return

    try:
        text = p.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            envelope["checks"]["ledger"] = {
                "available": True, "path": str(p), "last_event": None,
            }
            envelope["errors"].append({
                "code": "ledger_empty",
                "message": "ledger file is empty",
                "detail": str(p),
            })
            return
        last_line = lines[-1]
        try:
            event = json.loads(last_line)
        except json.JSONDecodeError as je:
            envelope["checks"]["ledger"] = {
                "available": True, "path": str(p), "last_event": None,
            }
            envelope["errors"].append({
                "code": "ledger_parse_error",
                "message": "could not parse last ledger line",
                "detail": str(je),
            })
            return
        envelope["checks"]["ledger"] = {
            "available": True, "path": str(p), "last_event": event,
        }
    except (json.JSONDecodeError, TypeError) as exc:
        envelope["checks"]["ledger"] = {"available": False, "path": str(p)}
        envelope["errors"].append({
            "code": "ledger_read_error",
            "message": "failed to read ledger file",
            "detail": str(exc),
        })


def _cmd_budget(envelope: Dict[str, Any]) -> None:
    candidates = [
        "ops.capital_shield_v2",
        "ops.spend_gateway_v1",
    ]
    found: List[str] = []
    for mod_name in candidates:
        try:
            importlib.import_module(mod_name)
            found.append(mod_name)
        except (ImportError, SyntaxError):
            pass

    if found:
        envelope["checks"]["budget"] = {
            "available": True, "modules_found": found,
        }
    else:
        envelope["checks"]["budget"] = {"available": False}
        envelope["errors"].append({
            "code": "budget_unavailable",
            "message": "no budget modules found",
            "detail": f"tried: {candidates}",
        })


def _cmd_safety(envelope: Dict[str, Any]) -> None:
    candidates = [
        "ops.safety_middleware",
        "synapse.safety",
    ]
    found: List[str] = []
    for mod_name in candidates:
        try:
            importlib.import_module(mod_name)
            found.append(mod_name)
        except (ImportError, SyntaxError):
            pass

    if found:
        envelope["checks"]["safety"] = {
            "available": True, "modules_found": found,
        }
    else:
        envelope["checks"]["safety"] = {"available": False}
        envelope["errors"].append({
            "code": "safety_unavailable",
            "message": "no safety modules found",
            "detail": f"tried: {candidates}",
        })


def _cmd_all(
    envelope: Dict[str, Any],
    include_tests: bool = False,
    timeout_s: int = 900,
    ledger_path: str | None = None,
) -> None:
    _cmd_health(envelope)
    _cmd_flags(envelope)
    _cmd_last_ledger(envelope, ledger_path=ledger_path)
    _cmd_budget(envelope)
    _cmd_safety(envelope)
    if include_tests:
        _cmd_tests(envelope, timeout_s=timeout_s)

    # Build summary
    degraded_count = len(envelope["errors"])
    overall: str
    if not envelope["ok"]:
        overall = "RED"
    elif degraded_count > 0:
        overall = "YELLOW"
    else:
        overall = "GREEN"

    envelope["checks"]["summary"] = {
        "overall": overall,
        "degraded_count": degraded_count,
        "error_count": 0 if envelope["ok"] else 1,
    }


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    # Common args shared by all subcommands via parent parser
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", dest="output_json", action="store_true", default=True,
        help="JSON output (default)",
    )
    common.add_argument(
        "--pretty", dest="output_pretty", action="store_true", default=False,
        help="Human-readable output with ANSI colors",
    )
    common.add_argument(
        "--timeout-s", type=int, default=900,
        help="Subprocess timeout in seconds (default 900)",
    )
    common.add_argument(
        "--ledger-path", type=str, default=None,
        help="Path to ledger NDJSON file",
    )

    ap = argparse.ArgumentParser(
        prog="synapse-cli-cockpit",
        description="Cockpit status CLI",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health", parents=[common])
    sub.add_parser("flags", parents=[common])
    sub.add_parser("tests", parents=[common])
    sub.add_parser("last-ledger", parents=[common])
    sub.add_parser("budget", parents=[common])
    sub.add_parser("safety", parents=[common])
    p_all = sub.add_parser("all", parents=[common])
    p_all.add_argument(
        "--include-tests", action="store_true", default=False,
        help="Include pytest run in 'all' (slow)",
    )

    args = ap.parse_args(argv)
    envelope = _base_envelope(args.cmd)

    try:
        if args.cmd == "health":
            _cmd_health(envelope)
        elif args.cmd == "flags":
            _cmd_flags(envelope)
        elif args.cmd == "tests":
            _cmd_tests(envelope, timeout_s=args.timeout_s)
        elif args.cmd == "last-ledger":
            _cmd_last_ledger(envelope, ledger_path=args.ledger_path)
        elif args.cmd == "budget":
            _cmd_budget(envelope)
        elif args.cmd == "safety":
            _cmd_safety(envelope)
        elif args.cmd == "all":
            _cmd_all(
                envelope,
                include_tests=args.include_tests,
                timeout_s=args.timeout_s,
                ledger_path=args.ledger_path,
            )
    except Exception as exc:
        envelope["ok"] = False
        envelope["errors"].append({
            "code": "cockpit_internal_error",
            "message": str(exc),
            "detail": type(exc).__name__,
        })

    exit_code = _compute_exit(envelope)

    if args.output_pretty:
        _print_pretty(envelope)
    else:
        _print_json(envelope)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
