from __future__ import annotations

import argparse

from synapse.cli.commands._invoke import invoke_module


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("doctor", help="Run infra doctor checks (read-only).")
    p.set_defaults(_fn=_run)


def _run(args: argparse.Namespace) -> int:
    # Lazy import via invoke_module (keeps init hygiene)
    # Doctor already verified GREEN in this repo state.
    return invoke_module("synapse.infra.doctor", argv=[])
