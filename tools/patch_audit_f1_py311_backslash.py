from __future__ import annotations

import re
import sys
from pathlib import Path
import py_compile

P = Path("tools/audit_f1.py")

def main() -> int:
    if not P.exists():
        print("MISSING: tools/audit_f1.py")
        return 2

    text = P.read_text(encoding="utf-8")

    # Match EXACT pattern that breaks on Py3.11:
    # hits.append(f"{rel.as_posix().replace('/','\\\\')}:{i}:{line.strip()}")
    rx = re.compile(
        r'^(?P<ind>\s*)hits\.append\(f"\{rel\.as_posix\(\)\.replace\('
        r"'/','\\\\\\\\'\)\}:\{i\}:\{line\.strip\(\)\\}\"\)\s*$",
        re.M,
    )
    m = rx.search(text)
    if not m:
        # fallback: any f-string expression containing replace('/','\\\\') inside braces
        rx2 = re.compile(r"\{[^}]*replace\('/','\\\\\\\\'\)[^}]*\}", re.M)
        if not rx2.search(text):
            print("NEEDLE_NOT_FOUND: no offending f-string found (maybe already fixed).")
            # still validate compile
            py_compile.compile(str(P), doraise=True)
            print("compile_ok=1")
            return 0
        print("FOUND_BACKSLASH_IN_FSTRING_BUT_PATTERN_CHANGED: abort to avoid blind patch")
        return 3

    ind = m.group("ind")
    # Replace with precomputed variable OUTSIDE f-string braces (legal on Py3.11)
    repl = (
        f"{ind}rel_s = rel.as_posix().replace('/', '\\\\')\n"
        f"{ind}hits.append(f\"{{rel_s}}:{{i}}:{{line.strip()}}\")"
    )

    new_text = rx.sub(repl, text, count=1)
    P.write_text(new_text, encoding="utf-8")

    # Hard validation: file must compile
    py_compile.compile(str(P), doraise=True)
    print("patched=1 compile_ok=1")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())