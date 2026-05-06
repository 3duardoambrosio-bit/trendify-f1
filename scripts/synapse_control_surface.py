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
        if "--help" not in command.argv:
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="synapse_control_surface",
        description="Local-only SYNAPSE control surface. No live, no spend, no secrets.",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--json", action="store_true")
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
