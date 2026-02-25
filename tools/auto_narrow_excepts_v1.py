# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
import tokenize
from typing import Iterable

# Only builtins / stdlib-safe names (no third-party).
# We prefer tuples that are narrower than Exception but still realistic.
PATTERN_PRIORITY = [
    ("INT_FLOAT_PARSE", ("ValueError", "TypeError")),
    ("JSON_LOADS_PARSE", ("ValueError", "TypeError")),  # JSONDecodeError ⊂ ValueError; keep stdlib-only without imports.
    ("SUBSCRIPT_ACCESS", ("KeyError", "IndexError", "TypeError")),
    ("ATTRIBUTE_ACCESS", ("AttributeError",)),
    ("FILE_IO", ("OSError", "UnicodeDecodeError")),
]

EXCEPT_LINE_RE = re.compile(
    r'^(?P<indent>\s*)except\s+Exception'
    r'(?P<aspart>\s+as\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*))?\s*:\s*(#.*)?$'
)

@dataclass(frozen=True)
class Candidate:
    file: str
    lineno: int
    excs: tuple[str, ...]
    pattern: str

def read_text(p: Path) -> str:
    with tokenize.open(p) as f:
        return f.read()

def write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")

def is_except_exception(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    return isinstance(t, ast.Name) and t.id == "Exception"

def iter_try_handlers(tree: ast.AST) -> Iterable[tuple[ast.Try, ast.ExceptHandler]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for h in node.handlers:
                if isinstance(h, ast.ExceptHandler):
                    yield node, h

def call_sig(fn: ast.AST) -> str | None:
    # Return "int", "float", "json.loads", "Path.read_text", etc when safely reconstructable.
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        # a.b
        if isinstance(fn.value, ast.Name):
            return f"{fn.value.id}.{fn.attr}"
        # Path(...).read_text -> value is Call; we only care about ".read_text"/".open" etc
        if isinstance(fn.value, ast.Call) and isinstance(fn.value.func, ast.Name):
            return f"{fn.value.func.id}.{fn.attr}"
        if isinstance(fn.value, ast.Call) and isinstance(fn.value.func, ast.Attribute):
            # pathlib.Path(...).read_text might show as Attribute chain; keep just attr
            return fn.attr
    return None

def stmt_complexity(try_node: ast.Try) -> tuple[int, int, int]:
    # (num_statements, num_calls, num_attrs)
    stmts = len(try_node.body)
    calls = 0
    attrs = 0
    for n in ast.walk(ast.Module(body=try_node.body, type_ignores=[])):
        if isinstance(n, ast.Call):
            calls += 1
        if isinstance(n, ast.Attribute):
            attrs += 1
    return stmts, calls, attrs

def detect_pattern(try_node: ast.Try) -> tuple[str, tuple[str, ...]] | None:
    # Guardrail: keep tries small to avoid semantic breakage.
    stmts, calls, attrs = stmt_complexity(try_node)
    if stmts > 6:
        return None

    sigs: list[str] = []
    has_subscript = False
    has_attr_access = False
    for n in ast.walk(ast.Module(body=try_node.body, type_ignores=[])):
        if isinstance(n, ast.Subscript):
            has_subscript = True
        if isinstance(n, ast.Attribute):
            has_attr_access = True
        if isinstance(n, ast.Call):
            s = call_sig(n.func)
            if s:
                sigs.append(s)

    sigset = set(sigs)

    # INT/FLOAT parsing
    if ("int" in sigset or "float" in sigset) and calls <= 4 and stmts <= 4:
        return "INT_FLOAT_PARSE", ("ValueError", "TypeError")

    # JSON parsing (std lib) - accept json.loads/json.load, also orjson.loads but still map to ValueError/TypeError
    if any(s.endswith(".loads") or s.endswith(".load") for s in sigset) and calls <= 4 and stmts <= 4:
        # narrow only if the sig includes json.loads/json.load OR orjson.loads-like; still safe w/ ValueError/TypeError.
        if any(s in {"json.loads","json.load","orjson.loads"} for s in sigset) or any(s.endswith(".loads") for s in sigset):
            return "JSON_LOADS_PARSE", ("ValueError", "TypeError")

    # File IO: open(), Path.read_text/write_text/read_bytes/write_bytes, Path.open
    if ("open" in sigset) or any(s in {"Path.read_text","Path.write_text","Path.read_bytes","Path.write_bytes","Path.open"} for s in sigset) \
       or any(s in {"read_text","write_text","read_bytes","write_bytes"} for s in sigset):
        if stmts <= 6:
            return "FILE_IO", ("OSError", "UnicodeDecodeError")

    # Subscript access (dict/list)
    if has_subscript and stmts <= 4 and calls <= 4:
        return "SUBSCRIPT_ACCESS", ("KeyError", "IndexError", "TypeError")

    # Attribute access (obj.attr) without huge call soup
    if has_attr_access and stmts <= 4 and calls <= 3:
        return "ATTRIBUTE_ACCESS", ("AttributeError",)

    return None

def patch_except_line(repo: Path, rel_file: str, lineno: int, excs: tuple[str, ...]) -> None:
    p = Path(rel_file)
    if p.is_absolute():
        try:
            p = p.relative_to(repo)
        except Exception:
            pass
    target = (repo / p).resolve()

    src = read_text(target)
    lines = src.splitlines(True)

    if lineno < 1 or lineno > len(lines):
        raise RuntimeError(f"lineno out of range: {p}:{lineno} (1..{len(lines)})")

    orig = lines[lineno - 1].rstrip("\r\n")
    m = EXCEPT_LINE_RE.match(orig)
    if not m:
        raise RuntimeError(f"line does not match 'except Exception' pattern: {p}:{lineno} -> {orig!r}")

    indent = m.group("indent") or ""
    var = m.group("var")

    excs_s = ", ".join(excs)
    new_line = indent + f"except ({excs_s})"
    if var:
        new_line += f" as {var}"
    new_line += ":"

    eol = "\n"
    if lines[lineno - 1].endswith("\r\n"):
        eol = "\r\n"
    lines[lineno - 1] = new_line + eol
    write_text(target, "".join(lines))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="synapse")
    ap.add_argument("--out", required=True, help="Output dir for report json")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    repo = Path.cwd()
    root = (repo / args.root).resolve()
    outdir = (repo / args.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    candidates: list[Candidate] = []

    for py in root.rglob("*.py"):
        try:
            txt = read_text(py)
            tree = ast.parse(txt)
        except Exception:
            continue

        for try_node, handler in iter_try_handlers(tree):
            if not is_except_exception(handler):
                continue

            # Prefer handler.lineno (line of 'except'); fallback conservative.
            lineno = getattr(handler, "lineno", None)
            if not isinstance(lineno, int) or lineno <= 0:
                continue

            det = detect_pattern(try_node)
            if not det:
                continue
            pattern, excs = det

            candidates.append(Candidate(str(py), lineno, excs, pattern))

    # Deterministic ordering
    candidates.sort(key=lambda c: (c.file, c.lineno, c.pattern))

    n = min(max(args.limit, 0), len(candidates))
    print(f"[INFO] candidates_available={len(candidates)} n_to_apply={n}")
    chosen = candidates[:n]

    report = {
        "root": str(root),
        "candidates_available": len(candidates),
        "chosen": [
            {"file": c.file, "lineno": c.lineno, "excs": list(c.excs), "pattern": c.pattern}
            for c in chosen
        ],
    }
    (outdir / "AUTO_NARROW_REPORT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    changed = 0
    if args.apply:
        for c in chosen:
            patch_except_line(repo, c.file, c.lineno, c.excs)
            print(f"[OK] {c.file}:{c.lineno} -> except ({', '.join(c.excs)}): via={c.pattern}")
            changed += 1

    print(f"[DONE] changed_sites={changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
