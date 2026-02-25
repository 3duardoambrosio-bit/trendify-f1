"""Cockpit status command: key=value parseable snapshot. S9."""

from __future__ import annotations

import io
import subprocess
import sys
from typing import Any, Dict, List


def _safe(fn, default="unknown"):
    """Run fn(); return default on any error. Never crash."""
    try:
        return fn()
    except Exception:
        return default


def _git_branch() -> str:
    p = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, timeout=10,
    )
    return p.stdout.strip() if p.returncode == 0 else "unknown"


def _git_head_short() -> str:
    p = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, timeout=10,
    )
    return p.stdout.strip() if p.returncode == 0 else "unknown"


def _git_dirty_lines() -> str:
    p = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, timeout=10,
    )
    if p.returncode != 0:
        return "unknown"
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    return str(len(lines))


def _doctor_overall() -> str:
    try:
        from synapse.infra.doctor import run_doctor
        overall, _ = run_doctor(verbose=False)
        return str(overall)
    except Exception:
        return "unknown"


def _feature_flags_info() -> Dict[str, Any]:
    try:
        from synapse.infra.feature_flags import FeatureFlags
        flags = FeatureFlags.load()
        return {
            "count": len(flags.values),
            "shopify_live": "1" if flags.is_on("shopify_live_api") else "0",
            "meta_live_api": "1" if flags.is_on("meta_live_api") else "0",
            "dropi_live_orders": "1" if flags.is_on("dropi_live_orders") else "0",
        }
    except Exception:
        return {
            "count": "unknown",
            "shopify_live": "unknown",
            "meta_live_api": "unknown",
            "dropi_live_orders": "unknown",
        }


def _budget_info() -> Dict[str, str]:
    try:
        from vault.vault import Vault
        import json
        from pathlib import Path

        state_path = Path("data/vault/vault_state.json")
        if not state_path.exists():
            return {"learning_spent": "unknown", "operational_spent": "unknown"}
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        return {
            "learning_spent": str(raw.get("learning_spent", "unknown")),
            "operational_spent": str(raw.get("operational_spent", "unknown")),
        }
    except (json.JSONDecodeError, TypeError):
        return {"learning_spent": "unknown", "operational_spent": "unknown"}


def _safety_killswitch() -> str:
    try:
        from synapse.safety.killswitch import KillSwitch, KillSwitchLevel
        from pathlib import Path
        import os

        state_file = Path(os.getenv(
            "SYNAPSE_KILLSWITCH_FILE", "data/safety/killswitch.json",
        ))
        ks = KillSwitch(state_file=state_file)
        if ks.is_active(KillSwitchLevel.SYSTEM):
            return "ACTIVE"
        return "inactive"
    except Exception:
        return "unknown"


def _ledger_last() -> Dict[str, str]:
    try:
        import json
        import os
        from pathlib import Path

        ledger_path = Path(os.getenv(
            "SYNAPSE_LEDGER_PATH", "data/ledger/ledger.ndjson",
        ))
        if not ledger_path.exists():
            return {"ts": "none", "type": "none"}
        text = ledger_path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return {"ts": "none", "type": "none"}
        last = json.loads(lines[-1])
        return {
            "ts": str(last.get("ts", "none")),
            "type": str(last.get("event_type", "none")),
        }
    except (json.JSONDecodeError, TypeError):
        return {"ts": "unknown", "type": "unknown"}


def print_status(stream=None) -> int:
    """Print a key=value parseable snapshot. Returns exit code 0."""
    if stream is None:
        stream = sys.stdout

    lines: List[str] = []
    lines.append("=== SYNAPSE COCKPIT STATUS ===")

    # Git
    lines.append(f"branch={_safe(_git_branch)}")
    lines.append(f"head_short={_safe(_git_head_short)}")
    lines.append(f"dirty_lines={_safe(_git_dirty_lines)}")

    # Doctor
    lines.append(f"doctor_overall={_safe(_doctor_overall)}")

    # Feature flags
    ff = _safe(_feature_flags_info, default={
        "count": "unknown", "shopify_live": "unknown",
        "meta_live_api": "unknown", "dropi_live_orders": "unknown",
    })
    lines.append(f"feature_flags_count={ff.get('count', 'unknown')}")
    lines.append(f"flag_shopify_live={ff.get('shopify_live', 'unknown')}")
    lines.append(f"flag_meta_live_api={ff.get('meta_live_api', 'unknown')}")
    lines.append(f"flag_dropi_live_orders={ff.get('dropi_live_orders', 'unknown')}")

    # Budget
    bi = _safe(_budget_info, default={
        "learning_spent": "unknown", "operational_spent": "unknown",
    })
    lines.append(f"budget_learning_spent={bi.get('learning_spent', 'unknown')}")
    lines.append(f"budget_operational_spent={bi.get('operational_spent', 'unknown')}")

    # Safety
    lines.append(f"safety_killswitch={_safe(_safety_killswitch)}")

    # Ledger
    ll = _safe(_ledger_last, default={"ts": "unknown", "type": "unknown"})
    lines.append(f"ledger_last_event_ts={ll.get('ts', 'unknown')}")
    lines.append(f"ledger_last_event_type={ll.get('type', 'unknown')}")

    # Exit
    lines.append("exit_code=0")

    for line in lines:
        stream.write(line + "\n")

    return 0


def register(sub) -> None:
    """Register as subcommand in synapse.cli."""
    import argparse
    p = sub.add_parser("status", help="Print cockpit status snapshot (key=value).")
    p.set_defaults(_fn=_run)


def _run(args) -> int:
    return print_status()


if __name__ == "__main__":
    raise SystemExit(print_status())
