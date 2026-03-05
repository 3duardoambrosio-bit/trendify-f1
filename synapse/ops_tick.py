"""ops_tick — Level 4 (NASA Power-of-Ten Grade).

Orchestrates the Phase-1 loop end-to-end via subprocess calls.
No direct money-path logic; delegates to specialised modules.

S19: Added reconcile pre-flight gate + alert emission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import deal

from synapse.infra.cli_logging import cli_print

_MARKER = "OPS_TICK_2026-03-04_V4_S19_RECONCILE_ALERT"
_LEDGER_REL = Path("data/ledger/events.ndjson")


# ── Value Objects ─────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class TickConfig:
    """Immutable parsed CLI configuration."""

    csv: str
    platform: str
    product_id: str
    prune: bool
    no_import: bool
    effective_readonly: bool


@dataclass(frozen=True, slots=True)
class StepResult:
    """Immutable result of a single pipeline step."""

    cmd: str
    returncode: int
    stdout_tail: str
    stderr_tail: str


# ── Private Helpers ───────────────────────────────────────

def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _run(
    cmd: List[str],
    env_overrides: Optional[Dict[str, str]] = None,
) -> StepResult:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    p = subprocess.run(
        cmd, capture_output=True, text=True,
        env=env, cwd=str(Path.cwd()),
    )
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    return StepResult(
        cmd=" ".join(cmd),
        returncode=p.returncode,
        stdout_tail=out[-2000:] if len(out) > 2000 else out,
        stderr_tail=err[-2000:] if len(err) > 2000 else err,
    )


def _skip_step(name: str, reason: str) -> StepResult:
    return StepResult(
        cmd=f"<SKIP> {name}", returncode=0,
        stdout_tail=reason, stderr_tail="",
    )


def _parse_tick_config(argv: Optional[List[str]] = None) -> TickConfig:
    ap = argparse.ArgumentParser(prog="synapse.ops_tick")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--no-import", action="store_true")
    ap.add_argument("--csv", default="auto")
    ap.add_argument("--platform", default="meta")
    ap.add_argument("--product-id", default="34357")
    ap.add_argument("--readonly", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    return TickConfig(
        csv=str(args.csv),
        platform=str(args.platform),
        product_id=str(args.product_id),
        prune=bool(args.prune),
        no_import=bool(args.no_import),
        effective_readonly=bool(
            args.readonly or (args.no_import and not args.write)
        ),
    )


def _execute_steps(config: TickConfig) -> List[StepResult]:
    env = {"SYNAPSE_READONLY": "1"} if config.effective_readonly else {}
    py = sys.executable
    steps: List[StepResult] = []

    if config.prune:
        steps.append(_run([py, "-m", "synapse.phase1_ready", "--prune"], env))

    steps.append(_run([py, "-m", "synapse.ledger_ndjson", "validate"], env))

    if not config.no_import:
        steps.append(_run([
            py, "-m", "synapse.ad_results_import",
            "--csv", config.csv,
            "--platform", config.platform,
            "--product-id", config.product_id,
        ], env))

    if config.no_import and config.effective_readonly:
        steps.append(_skip_step("synapse.runner", "no-import + readonly"))
    else:
        steps.append(_run([py, "-m", "synapse.runner"], env))

    steps.append(_run([py, "-m", "synapse.post_learning"], env))
    steps.append(_run([py, "-m", "synapse.creative_queue"], env))
    steps.append(_run([py, "-m", "synapse.creative_briefs"], env))
    return steps


def _compute_status(
    steps: List[StepResult],
    checks: Dict[str, Any],
) -> str:
    for s in steps:
        if s.returncode != 0:
            return "FAIL"
    if checks.get("readonly_invariant_ok") is False:
        return "FAIL"
    return "OK"


def _readonly_checks(
    ledger_path: Path,
    hash_before: Optional[str],
    effective_readonly: bool,
) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    if hash_before is not None:
        checks["ledger_hash_before"] = hash_before
    if ledger_path.exists() and hash_before is not None:
        after = _sha256(ledger_path)
        checks["ledger_hash_after"] = after
        if effective_readonly:
            ok = hash_before == after
            checks["readonly_invariant_ok"] = ok
            if not ok:
                checks["readonly_invariant_reason"] = "ledger mutated"
    return checks


def _persist_report(report: Dict[str, Any]) -> None:
    out_path = Path("data/run/ops_tick.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2,
                   sort_keys=True, default=str),
        encoding="utf-8",
    )
    cli_print(json.dumps(
        report, ensure_ascii=False, indent=2,
        sort_keys=True, default=str,
    ))


# ── S19: Reconcile Pre-flight Gate ────────────────────────

def _reconcile_preflight() -> Dict[str, Any]:
    """
    Pre-flight reconcile gate.

    Reads SYNAPSE_RECONCILE_ORDERS and SYNAPSE_RECONCILE_LEDGER from env.
    If both set, runs Shopify↔Ledger reconciliation.
    If blocked → returns gate result with blocked=True + emits alert.
    If env vars not set → skips (not mandatory, returns ok).
    """
    from synapse.infra.alert_wiring import get_alert_sink

    orders_path = os.environ.get("SYNAPSE_RECONCILE_ORDERS", "").strip()
    ledger_path = os.environ.get("SYNAPSE_RECONCILE_LEDGER", "").strip()

    if not orders_path or not ledger_path:
        return {"gate": "reconcile", "status": "skipped", "reason": "env_vars_not_set", "blocked": False}

    try:
        from synapse.infra.shopify_ledger_reconcile import (
            ReconcileConfig,
            load_json_any,
            load_ledger_any,
            reconcile_shopify_vs_ledger,
        )

        shop = load_json_any(orders_path)
        led = load_ledger_any(ledger_path)
        cfg = ReconcileConfig(require_shopify_paid_only=True)
        result = reconcile_shopify_vs_ledger(shop, led, cfg)

        if result.blocked:
            sink = get_alert_sink()
            top_items = result.items[:5]
            msg = (
                f"RECONCILE BLOCKED: missing={result.missing_count} "
                f"mismatch={result.mismatch_count} extra={result.extra_count} "
                f"top={[(i.order_id, i.kind) for i in top_items]}"
            )
            sink.send(msg, level="CRITICAL", dedupe_key="reconcile_blocked")
            return {"gate": "reconcile", "status": "BLOCKED", "blocked": True, "detail": msg}

        return {"gate": "reconcile", "status": "PASS", "blocked": False,
                "missing": result.missing_count, "mismatch": result.mismatch_count}

    except Exception as e:
        # FAIL-CLOSED: if reconcile crashes, block the tick
        sink = get_alert_sink()
        msg = f"RECONCILE EXCEPTION: {type(e).__name__}: {e}"
        sink.send(msg, level="CRITICAL", dedupe_key="reconcile_exception")
        return {"gate": "reconcile", "status": "ERROR", "blocked": True, "error": str(e)}


# ── Public Entry Point ────────────────────────────────────

@deal.pre(
    lambda argv=None: argv is None or isinstance(argv, list),
    message="argv must be None or list",
)
@deal.post(
    lambda result: result in (0, 2),
    message="main must return 0 (OK) or 2 (FAIL)",
)
def main(argv: Optional[List[str]] = None) -> int:
    """Run Phase-1 loop end-to-end."""
    config = _parse_tick_config(argv)
    repo = Path.cwd()
    ledger_path = repo / _LEDGER_REL

    # S19: Reconcile pre-flight gate (before any spending steps)
    reconcile_gate = _reconcile_preflight()
    if reconcile_gate.get("blocked"):
        report: Dict[str, Any] = {
            "marker": _MARKER,
            "ts": _utc_now_z(),
            "repo": str(repo),
            "inputs": asdict(config),
            "reconcile_gate": reconcile_gate,
            "steps": [],
            "status": "FAIL",
        }
        _persist_report(report)
        return 2

    hash_before = _sha256(ledger_path) if ledger_path.exists() else None
    steps = _execute_steps(config)
    checks = _readonly_checks(
        ledger_path, hash_before, config.effective_readonly,
    )
    status = _compute_status(steps, checks)

    # S19: Alert on tick failure
    if status == "FAIL":
        try:
            from synapse.infra.alert_wiring import get_alert_sink
            sink = get_alert_sink()
            failed = [s for s in steps if s.returncode != 0]
            msg = f"OPS_TICK FAILED: {len(failed)} step(s) failed"
            sink.send(msg, level="ERROR", dedupe_key="ops_tick_fail")
        except Exception:
            pass  # best-effort alerting

    report = {
        "marker": _MARKER,
        "ts": _utc_now_z(),
        "repo": str(repo),
        "inputs": asdict(config),
        "reconcile_gate": reconcile_gate,
        "checks": checks,
        "steps": [asdict(s) for s in steps],
        "status": status,
    }

    _persist_report(report)
    return 0 if status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
