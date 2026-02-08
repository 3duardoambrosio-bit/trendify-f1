from __future__ import annotations

import sys
from typing import Any, TextIO


def cli_print(*args: Any, sep: str = " ", end: str = "\n", file: TextIO | None = None, flush: bool = False) -> None:
    """
    Drop-in replacement for the built-in print without using it.
    Preserves message text, sep/end, stderr routing, and flush behavior.
    """
    stream: TextIO = sys.stdout if file is None else file

    # Only stdout/stderr are supported; anything else falls back to stdout to keep CLI safe.
    if stream is not sys.stderr:
        stream = sys.stdout

    msg = sep.join("" if a is None else str(a) for a in args)
    stream.write(msg + end)
    if flush:
        stream.flush()