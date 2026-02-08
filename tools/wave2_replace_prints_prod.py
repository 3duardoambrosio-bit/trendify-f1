from __future__ import annotations

import io
import tokenize
from pathlib import Path
from typing import List, Tuple

PROD_DIRS = [Path("synapse"), Path("infra"), Path("ops"), Path("buyer"), Path("core"), Path("config")]

# Skip canonicals (F1 rule)
CANONICALS = {
    Path("ops/capital_shield_v2.py"),
    Path("infra/ledger_v2.py"),
    Path("ops/spend_gateway_v1.py"),
    Path("ops/safety_middleware.py"),
    Path("synapse/safety/killswitch.py"),
    Path("synapse/safety/circuit.py"),
    Path("infra/atomic_io.py"),
    Path("infra/idempotency_manager.py"),
}

CLI_IMPORT = "from synapse.infra.cli_logging import cli_print"

def _read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def _write_utf8(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")

def _find_docstring_block(lines: List[str], start: int) -> Tuple[int, int]:
    i = start
    # skip blanks + comments
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
        ds = i
        # one-liner docstring
        if s.count(delim) >= 2:
            return ds, i + 1
        i += 1
        while i < len(lines) and delim not in lines[i]:
            i += 1
        if i < len(lines):
            return ds, i + 1
    return -1, -1

def _insert_cli_import(text: str) -> str:
    if CLI_IMPORT in text:
        return text

    lines = text.splitlines(True)
    i = 0

    # shebang
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    # encoding cookie
    if i < len(lines) and "coding" in lines[i]:
        i += 1

    # docstring
    ds, de = _find_docstring_block(lines, i)
    if ds != -1:
        i = de

    # after docstring: skip blanks
    while i < len(lines) and lines[i].strip() == "":
        i += 1

    # future imports block (must stay above everything)
    j = i
    while j < len(lines) and lines[j].startswith("from __future__ import"):
        j += 1
    if j != i:
        # skip one blank after future block if present
        if j < len(lines) and lines[j].strip() == "":
            j += 1
        ins = j
    else:
        ins = i

    out = lines[:ins]
    # ensure spacing
    if out and out[-1].strip() != "":
        out.append("\n")
    out.append(CLI_IMPORT + "\n")
    out.append("\n")
    out.extend(lines[ins:])
    return "".join(out)

def _replace_print_calls(text: str) -> Tuple[str, int]:
    buf = io.StringIO(text)
    toks = list(tokenize.generate_tokens(buf.readline))
    out_toks = []
    replaced = 0

    def prev_sig(k: int):
        j = k - 1
        while j >= 0 and toks[j].type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT):
            j -= 1
        return toks[j] if j >= 0 else None

    def next_sig(k: int):
        j = k + 1
        while j < len(toks) and toks[j].type in (tokenize.NL, tokenize.COMMENT):
            j += 1
        return toks[j] if j < len(toks) else None

    for k, t in enumerate(toks):
        if t.type == tokenize.NAME and t.string == "print":
            p = prev_sig(k)
            n = next_sig(k)
            # only direct print(...) calls, not obj.print(...)
            if (p is None or p.string != ".") and (n is not None and n.string == "("):
                t = tokenize.TokenInfo(t.type, "cli_print", t.start, t.end, t.line)
                replaced += 1
        out_toks.append(t)

    new_text = tokenize.untokenize(out_toks)
    return new_text, replaced

def main() -> int:
    changed_files = 0
    replaced_total = 0

    for root in PROD_DIRS:
        if not root.exists():
            continue
        for fp in root.rglob("*.py"):
            rel = fp.as_posix()
            p = Path(rel)

            if p in CANONICALS:
                continue

            text = _read_utf8(fp)
            new_text, replaced = _replace_print_calls(text)
            if replaced > 0:
                # ensure import only if we actually used cli_print
                new_text = _insert_cli_import(new_text)
                _write_utf8(fp, new_text)
                changed_files += 1
                replaced_total += replaced

    print(f"changed_files={changed_files}")
    print(f"replaced_print_calls={replaced_total}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())