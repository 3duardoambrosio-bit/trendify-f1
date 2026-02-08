from __future__ import annotations

import io
import tokenize
from pathlib import Path

TARGETS = [
    Path("synapse/ledger_ndjson.py"),
    Path("synapse/meta_publish_execute.py"),
    Path("synapse/infra/doctor.py"),
    Path("synapse/cli/commands/triage_cmd.py"),
    Path("synapse/cli/commands/wave_cmd.py"),
]

IMPORT_LINE = "from synapse.infra.cli_logging import cli_print\n"


def ensure_import(text: str) -> str:
    # If already imported, do nothing.
    if "from synapse.infra.cli_logging import cli_print" in text:
        return text

    lines = text.splitlines(True)

    # Keep shebang/encoding on top
    i = 0
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    if i < len(lines) and "coding" in lines[i]:
        i += 1

    # Handle module docstring ("""...""" or '''...''')
    def starts_doc(l: str) -> str | None:
        s = l.lstrip()
        if s.startswith('"""'):
            return '"""'
        if s.startswith("'''"):
            return "'''"
        return None

    while i < len(lines) and lines[i].strip() == "":
        i += 1

    delim = starts_doc(lines[i]) if i < len(lines) else None
    if delim is not None:
        # find closing delimiter
        if lines[i].lstrip().count(delim) >= 2:
            i += 1
        else:
            i += 1
            while i < len(lines) and delim not in lines[i]:
                i += 1
            if i < len(lines):
                i += 1

        # insert after docstring and one blank line
        if i < len(lines) and lines[i].strip() != "":
            lines.insert(i, "\n")
            i += 1

    lines.insert(i, IMPORT_LINE)
    return "".join(lines)


def replace_print_calls(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    src = ensure_import(src)

    buf = io.StringIO(src)
    out_tokens = []
    toks = list(tokenize.generate_tokens(buf.readline))

    def prev_significant(idx: int):
        j = idx - 1
        while j >= 0 and toks[j].type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT):
            j -= 1
        return toks[j] if j >= 0 else None

    def next_significant(idx: int):
        j = idx + 1
        while j < len(toks) and toks[j].type in (tokenize.NL, tokenize.COMMENT):
            j += 1
        return toks[j] if j < len(toks) else None

    for idx, t in enumerate(toks):
        if t.type == tokenize.NAME and t.string == "print":
            prev_t = prev_significant(idx)
            next_t = next_significant(idx)
            # Replace only direct calls: print(
            # Avoid attribute access: obj.print(
            if (prev_t is None or prev_t.string != ".") and (next_t is not None and next_t.string == "("):
                t = tokenize.TokenInfo(t.type, "cli_print", t.start, t.end, t.line)
        out_tokens.append(t)

    new_src = tokenize.untokenize(out_tokens)
    path.write_text(new_src, encoding="utf-8")


def main() -> int:
    for p in TARGETS:
        if not p.exists():
            raise SystemExit(f"MISSING_TARGET: {p}")
        replace_print_calls(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())