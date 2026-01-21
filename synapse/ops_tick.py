from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


__MARKER__ = "OPS_TICK_2026-01-13_V3_SAFE_NOIMPORT_SKIP_RUNNER"
LEDGER_REL = Path("data/ledger/events.ndjson")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _run(cmd: List[str], env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path.cwd()),
    )
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()

    return {
        "cmd": " ".join(cmd),
        "returncode": p.returncode,
        "stdout_tail": out[-2000:] if len(out) > 2000 else out,
        "stderr_tail": err[-2000:] if len(err) > 2000 else err,
    }


def _skip_step(name: str, reason: str) -> Dict[str, Any]:
    return {"cmd": f"<SKIP> {name}", "returncode": 0, "stdout_tail": reason, "stderr_tail": ""}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.ops_tick", description="Run Phase-1 loop end-to-end (no APIs).")
    ap.add_argument("--prune", action="store_true", help="Borra outputs stale para evitar 'stale brain'.")
    ap.add_argument("--no-import", action="store_true", help="No importa CSV; solo genera actions/creatives con weights existentes.")
    ap.add_argument("--csv", default="auto", help="CSV path o 'auto' (toma el más nuevo en ./exports).")
    ap.add_argument("--platform", default="meta", help="meta|tiktok|google")
    ap.add_argument("--product-id", default="34357", help="product id tag")
    ap.add_argument("--readonly", action="store_true", help="Fuerza SYNAPSE_READONLY=1 (no muta ledger).")
    ap.add_argument("--write", action="store_true", help="Permite writes aunque uses --no-import (override SAFE).")
    args = ap.parse_args(argv)

    # SAFE default:
    # si NO importas evidencia, corremos readonly (a menos que forces --write)
    effective_readonly = bool(args.readonly or (args.no_import and (not args.write)))
    env_over = {"SYNAPSE_READONLY": "1"} if effective_readonly else {}

    repo = Path.cwd()
    ledger_path = repo / LEDGER_REL

    report: Dict[str, Any] = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "repo": str(repo),
        "inputs": {
            "csv": args.csv,
            "platform": args.platform,
            "product_id": args.product_id,
            "prune": bool(args.prune),
            "no_import": bool(args.no_import),
            "readonly_flag": bool(args.readonly),
            "write_flag": bool(args.write),
            "effective_readonly": bool(effective_readonly),
        },
        "checks": {},
        "steps": [],
        "status": "OK",
    }

    # readonly invariant (if ledger exists)
    if ledger_path.exists():
        report["checks"]["ledger_hash_before"] = _sha256(ledger_path)

    # 0) optional prune
    if args.prune:
        report["steps"].append(_run([sys.executable, "-m", "synapse.phase1_ready", "--prune"], env_overrides=env_over))

    # 1) validate ledger
    report["steps"].append(_run([sys.executable, "-m", "synapse.ledger_ndjson", "validate"], env_overrides=env_over))

    # 2) import evidence (optional)
    if not args.no_import:
        report["steps"].append(
            _run(
                [
                    sys.executable,
                    "-m",
                    "synapse.ad_results_import",
                    "--csv",
                    str(args.csv),
                    "--platform",
                    str(args.platform),
                    "--product-id",
                    str(args.product_id),
                ],
                env_overrides=env_over,
            )
        )

    # 3) learn (solo si hay evidencia nueva o si explicitly permites writes)
    if args.no_import and effective_readonly:
        report["steps"].append(_skip_step("synapse.runner", "no-import + readonly => no learning (reuse existing weights.json)."))
    else:
        report["steps"].append(_run([sys.executable, "-m", "synapse.runner"], env_overrides=env_over))

    # 4) next actions
    report["steps"].append(_run([sys.executable, "-m", "synapse.post_learning"], env_overrides=env_over))

    # 5) creative queue
    report["steps"].append(_run([sys.executable, "-m", "synapse.creative_queue"], env_overrides=env_over))

    # 6) creative briefs
    report["steps"].append(_run([sys.executable, "-m", "synapse.creative_briefs"], env_overrides=env_over))

    # overall status by return codes
    for s in report["steps"]:
        if s.get("returncode", 0) != 0:
            report["status"] = "FAIL"
            break

    # readonly invariant check
    if ledger_path.exists():
        report["checks"]["ledger_hash_after"] = _sha256(ledger_path)
        if effective_readonly:
            ok = report["checks"]["ledger_hash_before"] == report["checks"]["ledger_hash_after"]
            report["checks"]["readonly_invariant_ok"] = bool(ok)
            if not ok:
                report["status"] = "FAIL"
                report["checks"]["readonly_invariant_reason"] = "ledger mutated under readonly"

    out_path = Path("data/run/ops_tick.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    report["out_path"] = str(out_path.resolve())

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())