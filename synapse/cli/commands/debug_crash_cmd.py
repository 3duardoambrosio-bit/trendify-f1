from __future__ import annotations

import argparse


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("debug-crash", help="[debug] Force a crash to validate CrashKit.")
    p.add_argument("--msg", default="debug crash", help="Crash message.")
    p.set_defaults(_fn=_run)


def _run(args: argparse.Namespace) -> int:
    raise RuntimeError(str(getattr(args, "msg", "debug crash")))
