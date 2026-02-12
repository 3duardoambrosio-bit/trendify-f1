from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse

from synapse.cli.commands._invoke import invoke_module


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("learning", help="Learning loop runner (default DRY-RUN).")
    mx = p.add_mutually_exclusive_group(required=False)
    mx.add_argument("--apply", action="store_true", help="Execute for real (turn off dry-run).")
    mx.add_argument("--dry-run", action="store_true", help="Force dry-run (no side effects).")
    p.set_defaults(_fn=_run)


def _run(args: argparse.Namespace) -> int:
    dry = True
    if getattr(args, "apply", False):
        dry = False
    if getattr(args, "dry_run", False):
        dry = True

    if dry:
        cli_print("learning: DRY-RUN — skipping execution. Use --apply to run learning_loop.", flush=True)
        return 0

    return invoke_module("synapse.learning.learning_loop", argv=[])
