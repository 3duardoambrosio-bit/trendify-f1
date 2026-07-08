from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SAFE_ID_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class ControlCommand:
    command_id: str
    label: str
    description: str
    argv: tuple[str, ...]
    category: str
    read_only: bool = True
    requires_secrets: bool = False
    live_allowed: bool = False
    writes_repo: bool = False
    functional_read_only: bool = False


def build_catalog(python_executable: str | None = None) -> tuple[ControlCommand, ...]:
    py = python_executable or sys.executable
    return (
        ControlCommand(
            "phase1_ready_help",
            "Phase 1 readiness help",
            "Inspect readiness CLI help only. No live operations.",
            (py, "-m", "synapse.phase1_ready", "--help"),
            "readiness",
        ),
        ControlCommand(
            "ops_summary_help",
            "Ops summary help",
            "Inspect local ops summary CLI help.",
            (py, "-m", "synapse.ops_summary", "--help"),
            "ops",
        ),
        ControlCommand(
            "meta_autopilot_help",
            "Meta autopilot help",
            "Inspect read-only Meta autopilot help. No live Meta API call.",
            (py, "-m", "synapse.meta_autopilot", "--help"),
            "marketing",
        ),
        ControlCommand(
            "post_learning_help",
            "Post-learning help",
            "Inspect local post-learning next-action help.",
            (py, "-m", "synapse.post_learning", "--help"),
            "learning",
        ),
        ControlCommand(
            "creative_queue_help",
            "Creative queue help",
            "Inspect creative queue CLI help.",
            (py, "-m", "synapse.creative_queue", "--help"),
            "creative",
        ),
        ControlCommand(
            "creative_briefs_help",
            "Creative briefs help",
            "Inspect creative briefs CLI help.",
            (py, "-m", "synapse.creative_briefs", "--help"),
            "creative",
        ),
        ControlCommand(
            "run_candidates_demo_help",
            "Candidates demo help",
            "Inspect offline candidates demo help. No Shopify, no Meta, no spend.",
            (py, "scripts/run_candidates_demo.py", "--help"),
            "demo",
        ),
        ControlCommand(
            "local_health",
            "Local health snapshot",
            "Emit a local read-only JSON health snapshot for the operator. No live, no spend, no secrets.",
            (py, "-S", "scripts/synapse_control_surface.py", "--health"),
            "health",
            functional_read_only=True,
        ),
        ControlCommand(
            "local_recent_decisions",
            "Local recent decisions",
            "Emit recent local decision/event ledger entries as JSON. No live, no spend, no secrets.",
            (py, "-S", "scripts/synapse_control_surface.py", "--recent-decisions"),
            "health",
            functional_read_only=True,
        ),
        ControlCommand(
            "local_safety_status",
            "Local safety status",
            "Emit local read-only safety gate status. No live, no spend, no secrets.",
            (py, "-S", "scripts/synapse_control_surface.py", "--safety-status"),
            "health",
            functional_read_only=True,
        ),
    )


def build_guarded_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["SYNAPSE_DRY_RUN"] = "1"
    env["SYNAPSE_NO_LIVE"] = "1"
    env["SYNAPSE_ALLOW_NETWORK"] = "0"
    env["SYNAPSE_ALLOW_SPEND"] = "0"
    env["SYNAPSE_CONTROL_SURFACE"] = "LOCAL_ONLY"
    env["SHOPIFY"] = "PAUSED"
    return env


def validate_catalog(catalog: Sequence[ControlCommand]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()

    for command in catalog:
        if not SAFE_ID_RE.match(command.command_id):
            errors.append(f"invalid command_id: {command.command_id}")
        if command.command_id in seen:
            errors.append(f"duplicate command_id: {command.command_id}")
        seen.add(command.command_id)

        if not command.argv:
            errors.append(f"empty argv: {command.command_id}")
        if not command.read_only:
            errors.append(f"not read_only: {command.command_id}")
        if command.requires_secrets:
            errors.append(f"requires_secrets: {command.command_id}")
        if command.live_allowed:
            errors.append(f"live_allowed: {command.command_id}")
        if command.writes_repo:
            errors.append(f"writes_repo: {command.command_id}")
        if "--help" not in command.argv and not command.functional_read_only:
            errors.append(f"not_help_only: {command.command_id}")

    if len(catalog) < 6:
        errors.append("catalog_too_small")

    return errors


def get_command(command_id: str, catalog: Sequence[ControlCommand]) -> ControlCommand:
    for command in catalog:
        if command.command_id == command_id:
            return command
    raise KeyError(f"unknown local control command: {command_id}")


def catalog_as_dicts(catalog: Sequence[ControlCommand]) -> list[dict[str, object]]:
    return [asdict(command) for command in catalog]


def run_control_command(command_id: str, timeout_s: int = 15) -> int:
    catalog = build_catalog()
    errors = validate_catalog(catalog)
    if errors:
        for error in errors:
            print(f"CATALOG_ERROR={error}", file=sys.stderr)
        return 2

    try:
        command = get_command(command_id, catalog)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    completed = subprocess.run(
        command.argv,
        cwd=ROOT,
        env=build_guarded_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    return int(completed.returncode)



def _run_git(args: Sequence[str]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
        )
        return {
            "rc": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }
    except Exception as exc:
        return {
            "rc": 1,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def build_health_payload() -> dict[str, object]:
    env = build_guarded_env({})
    catalog = build_catalog()
    catalog_errors = validate_catalog(catalog)

    head_short = _run_git(("rev-parse", "--short", "HEAD"))
    head_full = _run_git(("rev-parse", "HEAD"))
    status = _run_git(("status", "--short"))
    status_lines = [line for line in str(status["stdout"]).splitlines() if line.strip()]

    required_files = {
        "AGENTS.md": (ROOT / "AGENTS.md").exists(),
        "docs/local_control_surface_contract.md": (ROOT / "docs" / "local_control_surface_contract.md").exists(),
        "scripts/synapse_control_surface.py": (ROOT / "scripts" / "synapse_control_surface.py").exists(),
        "tests/p0/test_local_control_surface_contract.py": (
            ROOT / "tests" / "p0" / "test_local_control_surface_contract.py"
        ).exists(),
    }

    return {
        "schema": "synapse.local_control_surface.health.v1",
        "repo": {
            "root": str(ROOT),
            "head_short": head_short["stdout"],
            "head_full": head_full["stdout"],
            "git_status_count": len(status_lines),
            "git_status_clean": len(status_lines) == 0,
            "git_status_preview": status_lines[:20],
        },
        "control_surface": {
            "ok": len(catalog_errors) == 0,
            "catalog_count": len(catalog),
            "catalog_errors": catalog_errors,
            "command_ids": [command.command_id for command in catalog],
            "local_only": True,
        },
        "boundaries": {
            "SYNAPSE_DRY_RUN": env["SYNAPSE_DRY_RUN"],
            "SYNAPSE_NO_LIVE": env["SYNAPSE_NO_LIVE"],
            "SYNAPSE_ALLOW_NETWORK": env["SYNAPSE_ALLOW_NETWORK"],
            "SYNAPSE_ALLOW_SPEND": env["SYNAPSE_ALLOW_SPEND"],
            "SYNAPSE_CONTROL_SURFACE": env["SYNAPSE_CONTROL_SURFACE"],
            "SHOPIFY": env["SHOPIFY"],
        },
        "required_files": required_files,
        "operator_gate": {
            "gate": "G3_FIRST_FUNCTIONAL_READ_ONLY_COMMAND",
            "status": "PASS",
            "next": "add more read-only operational commands one at a time",
        },
    }


def _load_local_recent_decisions(limit: int = 5) -> dict:
    """Read recent local decision/event ledger entries without network, spend, or live writes."""
    ledger_path = Path("data/ledger/events.ndjson")
    entries = []
    errors = []

    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    if not ledger_path.exists():
        return {
            "command_id": "local_recent_decisions",
            "source": str(ledger_path).replace("\\", "/"),
            "source_exists": False,
            "limit": limit,
            "count": 0,
            "decisions": [],
            "errors": [],
        }

    try:
        raw_lines = ledger_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {
            "command_id": "local_recent_decisions",
            "source": str(ledger_path).replace("\\", "/"),
            "source_exists": True,
            "limit": limit,
            "count": 0,
            "decisions": [],
            "errors": [f"LEDGER_READ_ERROR:{exc.__class__.__name__}"],
        }

    for line_no, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            errors.append(f"INVALID_JSON_LINE:{line_no}")
            continue

        if not isinstance(payload, dict):
            errors.append(f"NON_OBJECT_LINE:{line_no}")
            continue

        event_type = str(
            payload.get("event_type")
            or payload.get("type")
            or payload.get("kind")
            or payload.get("decision_type")
            or "unknown"
        )

        looks_like_decision = (
            "decision" in event_type.lower()
            or "gate" in event_type.lower()
            or "route" in event_type.lower()
            or "status" in payload
            or "decision" in payload
        )

        if not looks_like_decision:
            continue

        entries.append(
            {
                "line": line_no,
                "event_type": event_type,
                "status": payload.get("status"),
                "decision": payload.get("decision"),
                "reason": payload.get("reason"),
                "timestamp": payload.get("timestamp") or payload.get("ts") or payload.get("created_at"),
            }
        )

    recent = entries[-limit:]
    return {
        "command_id": "local_recent_decisions",
        "source": str(ledger_path).replace("\\", "/"),
        "source_exists": True,
        "limit": limit,
        "count": len(recent),
        "decisions": recent,
        "errors": errors[-10:],
    }


def _run_local_recent_decisions() -> int:
    print(json.dumps(_load_local_recent_decisions(), sort_keys=True, ensure_ascii=False))
    return 0




def _control_surface_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _local_source_record(path: str, role: str) -> dict[str, object]:
    local_path = Path(path)
    return {
        "path": path.replace("\\", "/"),
        "role": role,
        "exists": local_path.exists(),
    }


def _load_kill_switch_snapshot() -> dict[str, object]:
    candidate_paths = [
        "data/safety/killswitch.json",
        "data/safety/kill_switch.json",
        "data/runtime/killswitch.json",
        "data/runtime/kill_switch.json",
        ".synapse/killswitch.json",
        ".synapse/kill_switch.json",
    ]

    checked = []
    errors = []

    for candidate in candidate_paths:
        path = Path(candidate)
        checked.append(candidate.replace("\\", "/"))
        if not path.exists():
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {
                "state": "corrupt_fail_closed",
                "active": True,
                "fail_closed": True,
                "source": candidate.replace("\\", "/"),
                "source_exists": True,
                "checked_sources": checked,
                "errors": ["KILL_SWITCH_STATE_INVALID_JSON"],
            }
        except OSError as exc:
            return {
                "state": "read_error_fail_closed",
                "active": True,
                "fail_closed": True,
                "source": candidate.replace("\\", "/"),
                "source_exists": True,
                "checked_sources": checked,
                "errors": [f"KILL_SWITCH_STATE_READ_ERROR:{exc.__class__.__name__}"],
            }

        if not isinstance(payload, dict):
            return {
                "state": "invalid_shape_fail_closed",
                "active": True,
                "fail_closed": True,
                "source": candidate.replace("\\", "/"),
                "source_exists": True,
                "checked_sources": checked,
                "errors": ["KILL_SWITCH_STATE_NON_OBJECT"],
            }

        active = _control_surface_bool(
            payload.get("active", payload.get("enabled", payload.get("tripped"))),
            False,
        )

        return {
            "state": "active" if active else "inactive",
            "active": active,
            "fail_closed": False,
            "source": candidate.replace("\\", "/"),
            "source_exists": True,
            "checked_sources": checked,
            "level": payload.get("level"),
            "reason": payload.get("reason"),
            "errors": errors,
        }

    return {
        "state": "no_state_file",
        "active": False,
        "fail_closed": False,
        "source": None,
        "source_exists": False,
        "checked_sources": checked,
        "errors": errors,
    }


def _load_local_safety_status() -> dict[str, object]:
    guarded_env = build_guarded_env()

    dry_run_effective = _control_surface_bool(guarded_env.get("SYNAPSE_DRY_RUN"), True)
    no_live = _control_surface_bool(guarded_env.get("SYNAPSE_NO_LIVE"), True)
    network_allowed = _control_surface_bool(guarded_env.get("SYNAPSE_ALLOW_NETWORK"), False)
    spend_allowed = _control_surface_bool(guarded_env.get("SYNAPSE_ALLOW_SPEND"), False)

    sources = [
        _local_source_record("config/feature_flags.py", "feature_flags"),
        _local_source_record("infra/network_guard.py", "network_guard"),
        _local_source_record("synapse/infra/dry_run.py", "dry_run"),
        _local_source_record("synapse/safety/killswitch.py", "kill_switch"),
        _local_source_record("synapse/infra/circuit_breaker.py", "circuit_breaker"),
        _local_source_record("synapse/safety/gate.py", "safety_gate"),
        _local_source_record("synapse/safety/limits.py", "risk_limits"),
        _local_source_record("ops/safety_middleware.py", "safety_middleware"),
        _local_source_record("ops/spend_gateway_v1.py", "spend_gateway"),
        _local_source_record("ops/capital_shield.py", "capital_shield_v1"),
        _local_source_record("ops/capital_shield_v2.py", "capital_shield_v2"),
        _local_source_record("synapse/meta/safe_client.py", "meta_safe_client"),
        _local_source_record("synapse/meta/publisher_contracts.py", "publisher_contracts"),
    ]

    source_map = {str(item["role"]): bool(item["exists"]) for item in sources}

    return {
        "command_id": "local_safety_status",
        "local_only": True,
        "read_only": True,
        "live_allowed": not no_live,
        "network_allowed": network_allowed,
        "spend_allowed": spend_allowed,
        "dry_run_effective": dry_run_effective,
        "shopify": guarded_env.get("SHOPIFY", "PAUSED"),
        "boundaries": {
            "SHOPIFY": guarded_env.get("SHOPIFY", "PAUSED"),
            "SYNAPSE_ALLOW_NETWORK": guarded_env.get("SYNAPSE_ALLOW_NETWORK", "0"),
            "SYNAPSE_ALLOW_SPEND": guarded_env.get("SYNAPSE_ALLOW_SPEND", "0"),
            "SYNAPSE_CONTROL_SURFACE": guarded_env.get("SYNAPSE_CONTROL_SURFACE", "LOCAL_ONLY"),
            "SYNAPSE_DRY_RUN": guarded_env.get("SYNAPSE_DRY_RUN", "1"),
            "SYNAPSE_NO_LIVE": guarded_env.get("SYNAPSE_NO_LIVE", "1"),
        },
        "kill_switch": _load_kill_switch_snapshot(),
        "capital_shield": {
            "source_exists": source_map.get("capital_shield_v1", False) or source_map.get("capital_shield_v2", False),
            "v1_source_exists": source_map.get("capital_shield_v1", False),
            "v2_source_exists": source_map.get("capital_shield_v2", False),
            "spend_gateway_source_exists": source_map.get("spend_gateway", False),
        },
        "safety_modules": {
            "network_guard_source_exists": source_map.get("network_guard", False),
            "dry_run_source_exists": source_map.get("dry_run", False),
            "kill_switch_source_exists": source_map.get("kill_switch", False),
            "circuit_breaker_source_exists": source_map.get("circuit_breaker", False),
            "safety_gate_source_exists": source_map.get("safety_gate", False),
            "risk_limits_source_exists": source_map.get("risk_limits", False),
            "safety_middleware_source_exists": source_map.get("safety_middleware", False),
            "meta_safe_client_source_exists": source_map.get("meta_safe_client", False),
            "publisher_contracts_source_exists": source_map.get("publisher_contracts", False),
        },
        "sources": sources,
        "errors": [],
    }


def _run_local_safety_status() -> int:
    print(json.dumps(_load_local_safety_status(), sort_keys=True, ensure_ascii=False))
    return 0

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="synapse_control_surface",
        description="Local-only SYNAPSE control surface. No live, no spend, no secrets.",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--recent-decisions", action="store_true")
    parser.add_argument("--safety-status", action="store_true")
    parser.add_argument("--run", default="")
    args = parser.parse_args(argv)

    catalog = build_catalog()
    errors = validate_catalog(catalog)

    if args.check:
        for error in errors:
            print(f"CATALOG_ERROR={error}")
        print(f"LOCAL_CONTROL_SURFACE_OK={int(not errors)}")
        print("LIVE=0")
        print("SPEND=0")
        print("SECRETS=0")
        print("SHOPIFY=PAUSED")
        return 0 if not errors else 2

    if args.health:
        print(json.dumps(build_health_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    if args.recent_decisions:
        if errors:
            for error in errors:
                print(f"CATALOG_ERROR={error}")
            return 2
        return _run_local_recent_decisions()


    if args.safety_status:
        if errors:
            for error in errors:
                print(f"CATALOG_ERROR={error}")
            return 2
        return _run_local_safety_status()

    if args.list:
        for command in catalog:
            print(f"{command.command_id}\t{command.category}\t{command.label}")
        return 0 if not errors else 2

    if args.json:
        print(json.dumps(catalog_as_dicts(catalog), ensure_ascii=False, indent=2))
        return 0 if not errors else 2

    if args.run:
        return run_control_command(args.run)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
