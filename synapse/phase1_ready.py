from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
logger = logging.getLogger(__name__)


__MARKER__ = "PHASE1_READY_2026-01-13_V1"

LEDGER_REL = Path("data/ledger/events.ndjson")

STALE_PATHS = [
    Path("data/run/learning_next_actions.json"),
    Path("data/run/creative_queue.json"),
    Path("data/run/creative_briefs.json"),
    Path("data/run/creative_publish_state.json"),
    Path("data/run/creative_briefs"),
]


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _rm(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {"path": str(path), "removed": False, "reason": "missing"}
        if path.is_dir():
            for p in sorted(path.rglob("*"), reverse=True):
                try:
                    if p.is_file():
                        p.unlink()
                    elif p.is_dir():
                        p.rmdir()
                except Exception as e:
                    logger.debug("suppressed exception", exc_info=True)

            path.rmdir()
            return {"path": str(path), "removed": True, "type": "dir"}
        path.unlink()
        return {"path": str(path), "removed": True, "type": "file"}
    except Exception as e:
        return {"path": str(path), "removed": False, "error": repr(e)}


def _read_ledger_lines(repo: Path) -> List[str]:
    p = repo / LEDGER_REL
    if not p.exists():
        return []
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _ledger_contract_check(lines: List[str]) -> Dict[str, Any]:
    # contract mínimo: no vacío, JSON parseable, y debe existir ts_utc (o ts legacy) en eventos recientes
    if not lines:
        return {"ok": False, "reason": "ledger_empty"}

    sample = lines[-10:] if len(lines) >= 10 else lines
    bad: List[str] = []
    for ln in sample:
        try:
            ev = json.loads(ln)
            ts = (ev.get("ts_utc") or ev.get("ts") or "").strip()
            if not ts:
                bad.append(f"missing_ts keys={sorted(ev.keys())}")
        except Exception as e:
            bad.append(f"bad_json {repr(e)}")

    return {"ok": len(bad) == 0, "checked": len(sample), "bad": bad[:5]}


def _run_module(module: str, env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    p = subprocess.run(
        [sys.executable, "-m", module],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path.cwd()),
    )
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    tail = (out[-1200:] if len(out) > 1200 else out)
    etail = (err[-1200:] if len(err) > 1200 else err)
    return {
        "module": module,
        "returncode": p.returncode,
        "stdout_tail": tail,
        "stderr_tail": etail,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.phase1_ready")
    ap.add_argument("--prune", action="store_true", help="Borra outputs stale (data/run/*) para evitar 'stale brain'.")
    ap.add_argument("--pytest", action="store_true", help="Corre pytest -q (tarda más).")
    args = ap.parse_args(argv)

    repo = Path.cwd()
    ledger_path = repo / LEDGER_REL

    report: Dict[str, Any] = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "repo": str(repo),
        "checks": {},
    }

    # optional prune
    if args.prune:
        report["prune"] = [_rm(repo / p) for p in STALE_PATHS]

    # ledger presence
    report["checks"]["ledger_exists"] = {"ok": ledger_path.exists(), "path": str(ledger_path)}
    lines = _read_ledger_lines(repo)
    report["checks"]["ledger_lines"] = {"count": len(lines)}
    report["checks"]["ledger_contract"] = _ledger_contract_check(lines)

    # readonly hash invariant (runner MUST NOT mutate ledger)
    if ledger_path.exists():
        before = _sha256(ledger_path)
        run = _run_module("synapse.runner", env_overrides={"SYNAPSE_READONLY": "1"})
        after = _sha256(ledger_path)
        report["checks"]["readonly_invariant"] = {
            "ok": before == after,
            "hash_before": before,
            "hash_after": after,
            "runner_rc": run["returncode"],
            "runner_stdout_tail": run["stdout_tail"],
            "runner_stderr_tail": run["stderr_tail"],
        }
    else:
        report["checks"]["readonly_invariant"] = {"ok": False, "reason": "ledger_missing"}

    # optional pytest
    if args.pytest:
        p = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True, cwd=str(repo))
        report["checks"]["pytest"] = {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout_tail": (p.stdout or "")[-1200:],
            "stderr_tail": (p.stderr or "")[-1200:],
        }

    # final
    ok = True
    for k, v in report["checks"].items():
        if isinstance(v, dict) and v.get("ok") is False:
            ok = False

    report["status"] = "OK" if ok else "FAIL"
    cli_print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())