"""ops_tick  Level 4 (NASA Power-of-Ten Grade).

Orchestrates the Phase-1 loop end-to-end via subprocess calls.
No direct money-path logic; delegates to specialised modules.

S19: Added reconcile pre-flight gate + alert emission.
S20: Added inventory pre-flight gate (fail-closed in write mode).
S22: In no-import + readonly mode, skip downstream creative steps that
depend on runner/import artifacts, avoiding false FAIL in scheduler mode.
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

_MARKER = "OPS_TICK_2026-03-09_V6_READONLY_SKIP_DOWNSTREAM"
_LEDGER_REL = Path("data/ledger/events.ndjson")


#
# Value Objects
#

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


#
# Private Helpers
#

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
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path.cwd()),
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
        cmd=f"<SKIP> {name}",
        returncode=0,
        stdout_tail=reason,
        stderr_tail="",
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

    readonly_no_import = config.no_import and config.effective_readonly

    if config.prune:
        steps.append(_run([py, "-m", "synapse.phase1_ready", "--prune"], env))

    steps.append(_run([py, "-m", "synapse.ledger_ndjson", "validate"], env))

    if not config.no_import:
        steps.append(_run([
            py,
            "-m",
            "synapse.ad_results_import",
            "--csv",
            config.csv,
            "--platform",
            config.platform,
            "--product-id",
            config.product_id,
        ], env))

    if readonly_no_import:
        steps.append(_skip_step("synapse.runner", "no-import + readonly"))
    else:
        steps.append(_run([py, "-m", "synapse.runner"], env))

    steps.append(_run([py, "-m", "synapse.post_learning"], env))

    if readonly_no_import:
        steps.append(
            _skip_step(
                "synapse.creative_queue",
                "no-import + readonly => skip downstream creative queue",
            )
        )
        steps.append(
            _skip_step(
                "synapse.creative_briefs",
                "no-import + readonly => skip downstream creative briefs",
            )
        )
    else:
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

    reconcile = checks.get("reconcile_preflight") or {}
    if reconcile.get("blocked") is True:
        return "FAIL"

    inventory = checks.get("inventory_preflight") or {}
    if inventory.get("blocked") is True:
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
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    cli_print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


def _emit_alert(text: str) -> None:
    try:
        from synapse.infra.alert_wiring import get_alert_sink

        sink = get_alert_sink()
        sink.send(text)
    except Exception:
        # fail-closed for core gate logic, fail-open for alert transport
        pass


#
# S20: Inventory Pre-flight Gate
#

def _load_inventory_any(path: str) -> Any:
    p = Path(path)
    txt = p.read_text(encoding="utf-8-sig")
    lines = [ln for ln in txt.splitlines() if ln.strip()]

    if p.suffix.lower() in (".ndjson", ".jsonl"):
        return [json.loads(ln) for ln in lines]

    if len(lines) >= 2 and not txt.lstrip().startswith("[") and not txt.lstrip().startswith("{"):
        return [json.loads(ln) for ln in lines]

    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        if len(lines) >= 1:
            return [json.loads(ln) for ln in lines]
        raise


def _extract_inventory_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        for key in ("products", "items", "data", "objects", "top"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        return [payload]

    raise ValueError("unsupported_inventory_shape")


def _coerce_stock(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    s = str(value).strip()
    if s == "":
        return None
    if s.lstrip("-").isdigit():
        return int(s)
    try:
        f = float(s)
        if f.is_integer():
            return int(f)
    except Exception:
        return None
    return None


def _inventory_row_matches(row: Dict[str, Any], product_id: str) -> bool:
    pid = str(product_id).strip()
    for key in ("source_product_id", "product_id", "id", "sku"):
        if key in row and row[key] is not None:
            if str(row[key]).strip() == pid:
                return True
    return False


def _inventory_preflight(product_id: str, effective_readonly: bool) -> Dict[str, Any]:
    """
    Inventory gate.

    Env:
      SYNAPSE_INVENTORY_CATALOG = path to JSON / NDJSON inventory snapshot

    Rules:
    - readonly + no env => skipped
    - write mode + no env => BLOCKED
    - product missing => BLOCKED
    - stock missing => BLOCKED
    - stock <= 0 => BLOCKED
    - stock > 0 => PASS
    """
    catalog_path = os.environ.get("SYNAPSE_INVENTORY_CATALOG", "").strip()

    if not catalog_path:
        if effective_readonly:
            return {
                "gate": "inventory",
                "status": "skipped",
                "reason": "env_var_not_set",
                "blocked": False,
            }

        result = {
            "gate": "inventory",
            "status": "BLOCKED",
            "reason": "env_var_not_set",
            "blocked": True,
            "product_id": str(product_id),
        }
        _emit_alert(
            f"INVENTORY BLOCKED product_id={product_id} reason=env_var_not_set"
        )
        return result

    try:
        payload = _load_inventory_any(catalog_path)
        rows = _extract_inventory_rows(payload)
    except Exception as e:
        result = {
            "gate": "inventory",
            "status": "BLOCKED",
            "reason": f"inventory_load_error:{type(e).__name__}",
            "blocked": True,
            "product_id": str(product_id),
            "catalog_path": catalog_path,
        }
        _emit_alert(
            f"INVENTORY BLOCKED product_id={product_id} "
            f"reason=inventory_load_error catalog={catalog_path}"
        )
        return result

    target: Optional[Dict[str, Any]] = None
    for row in rows:
        if _inventory_row_matches(row, product_id):
            target = row
            break

    if target is None:
        result = {
            "gate": "inventory",
            "status": "BLOCKED",
            "reason": "product_not_found",
            "blocked": True,
            "product_id": str(product_id),
            "catalog_path": catalog_path,
        }
        _emit_alert(
            f"INVENTORY BLOCKED product_id={product_id} reason=product_not_found"
        )
        return result

    stock = _coerce_stock(target.get("stock"))
    if stock is None:
        result = {
            "gate": "inventory",
            "status": "BLOCKED",
            "reason": "stock_missing_or_invalid",
            "blocked": True,
            "product_id": str(product_id),
            "catalog_path": catalog_path,
        }
        _emit_alert(
            f"INVENTORY BLOCKED product_id={product_id} reason=stock_missing_or_invalid"
        )
        return result

    if stock <= 0:
        result = {
            "gate": "inventory",
            "status": "BLOCKED",
            "reason": "out_of_stock",
            "blocked": True,
            "product_id": str(product_id),
            "stock": stock,
            "catalog_path": catalog_path,
        }
        _emit_alert(
            f"INVENTORY BLOCKED product_id={product_id} reason=out_of_stock stock={stock}"
        )
        return result

    return {
        "gate": "inventory",
        "status": "PASS",
        "reason": "stock_available",
        "blocked": False,
        "product_id": str(product_id),
        "stock": stock,
        "catalog_path": catalog_path,
    }


#
# S19: Reconcile Pre-flight Gate
#

def _reconcile_preflight() -> Dict[str, Any]:
    """
    Pre-flight reconcile gate.

    Reads SYNAPSE_RECONCILE_ORDERS and SYNAPSE_RECONCILE_LEDGER from env.
    If both set, runs ShopifyLedger reconciliation.
    If blocked => returns gate result with blocked=True + emits alert.
    If env vars not set => skips (not mandatory, returns ok).
    """
    orders_path = os.environ.get("SYNAPSE_RECONCILE_ORDERS", "").strip()
    ledger_path = os.environ.get("SYNAPSE_RECONCILE_LEDGER", "").strip()

    if not orders_path or not ledger_path:
        return {
            "gate": "reconcile",
            "status": "skipped",
            "reason": "env_vars_not_set",
            "blocked": False,
        }

    try:
        from synapse.infra.shopify_ledger_reconcile import (
            ReconcileConfig,
            load_json_any,
            load_ledger_any,
            reconcile_shopify_vs_ledger,
        )

        shop = load_json_any(orders_path)
        led = load_ledger_any(ledger_path)

        r = reconcile_shopify_vs_ledger(
            shop,
            led,
            ReconcileConfig(require_shopify_paid_only=True),
        )

        result = {
            "gate": "reconcile",
            "status": "BLOCKED" if r.blocked else "PASS",
            "reason": "drift_detected" if r.blocked else "matched",
            "blocked": bool(r.blocked),
            "missing_count": int(r.missing_count),
            "mismatch_count": int(r.mismatch_count),
            "extra_count": int(r.extra_count),
        }

        if r.blocked:
            _emit_alert(
                "RECONCILE BLOCKED "
                f"missing={r.missing_count} mismatch={r.mismatch_count} extra={r.extra_count}"
            )

        return result

    except Exception as e:
        result = {
            "gate": "reconcile",
            "status": "ERROR",
            "reason": f"exception:{type(e).__name__}",
            "blocked": True,
        }
        _emit_alert(
            f"RECONCILE BLOCKED reason=exception type={type(e).__name__}"
        )
        return result


#
# Public entrypoint
#

@deal.pre(lambda argv=None: argv is None or isinstance(argv, list))
@deal.post(lambda result: result in (0, 2))
def main(argv: Optional[List[str]] = None) -> int:
    config = _parse_tick_config(argv)

    ledger_path = _LEDGER_REL
    hash_before: Optional[str] = _sha256(ledger_path) if ledger_path.exists() else None

    checks: Dict[str, Any] = {}

    inventory_gate = _inventory_preflight(
        product_id=config.product_id,
        effective_readonly=config.effective_readonly,
    )
    checks["inventory_preflight"] = inventory_gate

    reconcile_gate = _reconcile_preflight()
    checks["reconcile_preflight"] = reconcile_gate

    steps: List[StepResult] = []

    if not inventory_gate.get("blocked") and not reconcile_gate.get("blocked"):
        steps = _execute_steps(config)

    checks.update(
        _readonly_checks(
            ledger_path=ledger_path,
            hash_before=hash_before,
            effective_readonly=config.effective_readonly,
        )
    )

    status = _compute_status(steps, checks)

    report = {
        "marker": _MARKER,
        "ts_utc": _utc_now_z(),
        "status": status,
        "config": asdict(config),
        "checks": checks,
        "steps": [asdict(s) for s in steps],
    }

    _persist_report(report)
    return 0 if status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())