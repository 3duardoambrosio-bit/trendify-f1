from __future__ import annotations

from pathlib import Path

TARGETS = [
    Path("synapse/ledger_ndjson.py"),
    Path("synapse/meta_publish_execute.py"),
    Path("synapse/infra/doctor.py"),
    Path("synapse/cli/commands/triage_cmd.py"),
    Path("synapse/cli/commands/wave_cmd.py"),
]

FUTURE = "from __future__ import annotations"
CLIIMP = "from synapse.infra.cli_logging import cli_print"

def _split_keepends(text: str):
    return text.splitlines(True)

def _detect_docstring(lines: list[str], start: int) -> tuple[int, int]:
    """
    Returns (doc_start, doc_end_exclusive) if a top-level docstring exists at or after `start`,
    otherwise (-1, -1). Only considers the first non-empty, non-comment line.
    """
    i = start
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    while i < len(lines) and lines[i].lstrip().startswith("#"):
        i += 1
        while i < len(lines) and lines[i].strip() == "":
            i += 1

    if i >= len(lines):
        return -1, -1

    s = lines[i].lstrip()
    if s.startswith('"""') or s.startswith("'''"):
        delim = '"""' if s.startswith('"""') else "'''"
        doc_start = i
        # One-line docstring
        if s.count(delim) >= 2:
            return doc_start, i + 1
        # Multi-line: find closing
        i += 1
        while i < len(lines) and delim not in lines[i]:
            i += 1
        if i < len(lines):
            return doc_start, i + 1
    return -1, -1

def _normalize_header(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = _split_keepends(text)

    # Keep shebang + encoding (PEP 263) at top if present
    header = []
    i = 0
    if i < len(lines) and lines[i].startswith("#!"):
        header.append(lines[i]); i += 1
    if i < len(lines) and "coding" in lines[i]:
        header.append(lines[i]); i += 1

    # Docstring block (optional)
    doc_s, doc_e = _detect_docstring(lines, i)
    doc = []
    if doc_s != -1:
        # include any blank/comment lines between i and doc_s (rare)
        header.extend(lines[i:doc_s])
        doc = lines[doc_s:doc_e]
        i = doc_e
    else:
        # keep leading blanks/comments up to first statement as part of header
        # but stop before future/import rearrangement if possible
        header.extend([])

    # Collect the rest of the file from i onwards
    rest = lines[i:]

    # Remove existing FUTURE and CLIIMP lines anywhere in rest/header/doc to avoid duplicates
    def is_future(l: str) -> bool:
        return l.strip() == FUTURE
    def is_cli(l: str) -> bool:
        return l.strip() == CLIIMP

    # We only want to strip FUTURE/CLI from rest; header/doc stay as-is
    rest2 = [l for l in rest if not is_future(l) and not is_cli(l)]

    # Determine if FUTURE existed anywhere originally (header/doc/rest)
    had_future = any(is_future(l) for l in (header + doc + rest))
    if not had_future:
        # If target file somehow doesn't use it, we still won't force-add it.
        pass

    # Determine if cli_print import existed anywhere originally, or if file uses cli_print now.
    had_cli = any(is_cli(l) for l in (header + doc + rest))
    uses_cli_print = "cli_print(" in "".join(rest2)  # good enough for our case
    want_cli = had_cli or uses_cli_print

    out = []
    out.extend(header)
    out.extend(doc)

    # Ensure exactly one blank line after doc/header block if not already
    if out and out[-1].strip() != "":
        out.append("\n")

    # FUTURE must be first real statement after docstring
    if had_future:
        out.append(FUTURE + "\n")
        out.append("\n")

    # Put cli_print import immediately after future import (safe)
    if want_cli:
        out.append(CLIIMP + "\n")
        out.append("\n")

    out.extend(rest2)

    path.write_text("".join(out), encoding="utf-8")

def main() -> int:
    for p in TARGETS:
        if not p.exists():
            raise SystemExit(f"MISSING_TARGET: {p}")
        _normalize_header(p)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())