from __future__ import annotations

import re
from pathlib import Path
import py_compile

P = Path("tools/audit_f1.py")

def main() -> int:
    if not P.exists():
        print("MISSING=1")
        return 2

    text = P.read_text(encoding="utf-8")
    lines = text.splitlines(True)

    # Idempotente: si ya existe rel_s + hits.append(f"{rel_s}..."), solo compila.
    if ("rel_s = rel.as_posix().replace(" in text) and ('hits.append(f"{rel_s}:' in text):
        py_compile.compile(str(P), doraise=True)
        print("already_patched=1 compile_ok=1")
        return 0

    # Busca la línea ofensora: hits.append(f"... rel.as_posix().replace('/','\\\\') ...")
    idx = None
    for i, l in enumerate(lines):
        if (
            "hits.append(f" in l
            and "rel.as_posix().replace" in l
            and "line.strip()" in l
            and "\\\\" in l
        ):
            idx = i
            break

    if idx is None:
        # Si no lo encontramos, no hacemos edits ciegos.
        py_compile.compile(str(P), doraise=True)
        print("needle_not_found=1 compile_ok=1")
        return 0

    offending = lines[idx]
    indent = offending[: len(offending) - len(offending.lstrip(" \t"))]

    # Reemplazo Py3.11-safe: backslash fuera de expr del f-string
    repl = [
        f'{indent}rel_s = rel.as_posix().replace("/", "\\\\")\n',
        f'{indent}hits.append(f"{{rel_s}}:{{i}}:{{line.strip()}}")\n',
    ]
    lines[idx:idx+1] = repl

    P.write_text("".join(lines), encoding="utf-8")
    py_compile.compile(str(P), doraise=True)
    print("patched=1 compile_ok=1")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())