from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import os

from synapse.cli.commands._invoke import invoke_module


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("learning", help="Learning loop runner (default DRY-RUN).")
    mx = p.add_mutually_exclusive_group(required=False)
    mx.add_argument("--apply", action="store_true", help="Execute for real (turn off dry-run).")
    mx.add_argument("--dry-run", action="store_true", help="Force dry-run (no side effects).")
    p.set_defaults(_fn=_run)


def _readonly_enabled() -> bool:
    return os.getenv("SYNAPSE_READONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _emit_learning_output(
    *,
    status: str,
    dry_run: bool,
    apply_requested: bool,
    writes_allowed: bool,
    rc: int,
) -> None:
    cli_print(f"LEARNING_STATUS={status}", flush=True)
    cli_print(f"LEARNING_DRY_RUN={str(dry_run).lower()}", flush=True)
    cli_print(
        f"LEARNING_APPLY_REQUESTED={str(apply_requested).lower()}",
        flush=True,
    )
    cli_print(
        f"LEARNING_WRITES_ALLOWED={str(writes_allowed).lower()}",
        flush=True,
    )
    cli_print(f"LEARNING_RC={rc}", flush=True)


def _run(args: argparse.Namespace) -> int:
    dry = True
    if getattr(args, "apply", False):
        dry = False
    if getattr(args, "dry_run", False):
        dry = True

    if dry:
        cli_print("learning: DRY-RUN — skipping execution. Use --apply to run learning_loop.", flush=True)
        _emit_learning_output(
            status="DRY_RUN_NOOP" if getattr(args, "dry_run", False) else "DEFAULT_NOOP",
            dry_run=True,
            apply_requested=False,
            writes_allowed=False,
            rc=0,
        )
        return 0

    if _readonly_enabled():
        _emit_learning_output(
            status="READONLY_BLOCKED",
            dry_run=False,
            apply_requested=True,
            writes_allowed=False,
            rc=2,
        )
        return 2

    rc = invoke_module("synapse.learning.learning_loop", argv=["--apply"])
    if rc in (0, 2, 3):
        return rc

    _emit_learning_output(
        status="EXECUTION_ERROR",
        dry_run=False,
        apply_requested=True,
        writes_allowed=True,
        rc=3,
    )
    return 3
