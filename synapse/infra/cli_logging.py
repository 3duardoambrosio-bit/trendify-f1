from __future__ import annotations

import sys
from typing import Any, TextIO


def cli_print(*args: Any, sep: str = " ", end: str = "\n", file: TextIO | None = None, flush: bool = False) -> None:
    stream: TextIO = sys.stdout if file is None else file
    if stream is not sys.stderr:
        stream = sys.stdout

    msg = sep.join("" if a is None else str(a) for a in args)

    # Windows consoles may be cp1252. Force-safe output (replace unencodable chars).
    enc = getattr(stream, "encoding", None) or "utf-8"
    safe = msg.encode(enc, errors="replace").decode(enc, errors="replace")

    stream.write(safe + end)
    if flush:
        stream.flush()
