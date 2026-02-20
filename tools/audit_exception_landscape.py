from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tokenize


EXCLUDE_DIRS_DEFAULT = {
    ".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache",
    "dist", "build", ".ruff_cache", ".tox", "node_modules"
}

BROAD_TYPES = {"Exception", "BaseException"}  # bare handled separately


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _iter_py_files(root: Path, exclude_dirs: set[str]) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if any(d in parts for d in exclude_dirs):
            continue
        files.append(p)
    return sorted(files)


def _read_source_tokenize_open(p: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Reads source using tokenize.open (respects PEP 263 encoding cookie).
    Returns (src, error). error is None on success.
    """
    try:
        with tokenize.open(p) as f:
            return f.read(), None
    except Exception as e:
        return None, repr(e)


def _sha256_utf8(src: str) -> str:
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def _type_to_str(t: ast.AST) -> str:
    if isinstance(t, ast.Name):
        return t.id
    if isinstance(t, ast.Attribute):
        base = _type_to_str(t.value)
        return f"{base}.{t.attr}" if base else t.attr
    if isinstance(t, ast.Tuple):
        return "(" + ", ".join(_type_to_str(elt) for elt in t.elts) + ")"
    # fallback: class name
    return t.__class__.__name__


def _unparse(node: ast.AST) -> str:
    # ast.unparse available in Py 3.9+
    try:
        return ast.unparse(node)  # type: ignore[attr-defined]
    except Exception:
        return node.__class__.__name__


def _first_line_at(lines: List[str], lineno: Optional[int]) -> str:
    if not lineno or lineno < 1 or lineno > len(lines):
        return ""
    return lines[lineno - 1].rstrip("\n")


def _suggest_narrowing_for_try(try_node: ast.Try) -> List[str]:
    """
    Heuristics: if try-body contains calls that strongly imply specific exceptions,
    suggest narrowing. This is advisory only (NO mutations here).
    """
    callees: set[str] = set()
    for n in ast.walk(ast.Module(body=try_node.body, type_ignores=[])):
        if isinstance(n, ast.Call):
            callees.add(_unparse(n.func))

    suggestions: List[str] = []

    # high-confidence patterns
    if "int" in callees or "float" in callees:
        suggestions.append("ValueError, TypeError  (int/float)")
    if "json.loads" in callees:
        suggestions.append("json.JSONDecodeError, TypeError  (json.loads)")
    if "uuid.UUID" in callees:
        suggestions.append("ValueError  (uuid.UUID)")
    if "ast.literal_eval" in callees:
        suggestions.append("ValueError, SyntaxError  (ast.literal_eval)")
    if "importlib.import_module" in callees:
        suggestions.append("ImportError, ModuleNotFoundError  (import_module)")

    # file i/o patterns (still common, but slightly broader)
    io_like = [c for c in callees if c.endswith(".read_text") or c.endswith(".read_bytes")]
    if io_like:
        suggestions.append("OSError, FileNotFoundError, PermissionError, UnicodeDecodeError  (Path.read_*)")

    if "open" in callees:
        suggestions.append("OSError, FileNotFoundError, PermissionError  (open)")

    return suggestions


def analyze(root: Path, exclude_dirs: set[str]) -> Dict[str, Any]:
    py_files = _iter_py_files(root, exclude_dirs)

    out: Dict[str, Any] = {
        "root": str(root),
        "files_total": len(py_files),
        "files_scanned": 0,
        "read_errors": [],
        "syntax_errors": [],
        "counts": {
            "bare_except": 0,
            "except_Exception": 0,
            "except_BaseException": 0,
            "except_other": 0,
            "dyn_import_calls": 0,
        },
        "excepts": [],
        "dyn_imports": [],
        "top_files": [],
    }

    per_file_counts: Dict[str, Dict[str, int]] = {}

    for p in py_files:
        out["files_scanned"] += 1
        src, err = _read_source_tokenize_open(p)
        if err is not None or src is None:
            out["read_errors"].append({"file": str(p), "error": err})
            continue

        sha = _sha256_utf8(src)
        lines = src.splitlines()

        try:
            tree = ast.parse(src, filename=str(p))
        except SyntaxError as e:
            out["syntax_errors"].append({
                "file": str(p),
                "lineno": e.lineno,
                "offset": e.offset,
                "msg": e.msg,
                "text": (e.text or "").rstrip("\n"),
            })
            continue

        # pre-init file counters
        fkey = str(p)
        per_file_counts.setdefault(fkey, {"bare": 0, "Exception": 0, "BaseException": 0, "other": 0, "dyn": 0})

        # Walk Try nodes so we can attach narrowing suggestions to handlers
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                suggestions = _suggest_narrowing_for_try(node)
                for h in node.handlers:
                    et = h.type
                    if et is None:
                        kind = "bare"
                        out["counts"]["bare_except"] += 1
                        per_file_counts[fkey]["bare"] += 1
                        etype_str = None
                    else:
                        etype_str = _type_to_str(et)
                        if etype_str == "Exception":
                            kind = "Exception"
                            out["counts"]["except_Exception"] += 1
                            per_file_counts[fkey]["Exception"] += 1
                        elif etype_str == "BaseException":
                            kind = "BaseException"
                            out["counts"]["except_BaseException"] += 1
                            per_file_counts[fkey]["BaseException"] += 1
                        else:
                            kind = "other"
                            out["counts"]["except_other"] += 1
                            per_file_counts[fkey]["other"] += 1

                    header = _first_line_at(lines, getattr(h, "lineno", None)).strip()
                    body0 = ""
                    if h.body:
                        b0 = h.body[0]
                        body0 = _first_line_at(lines, getattr(b0, "lineno", None)).strip()

                    out["excepts"].append({
                        "file": fkey,
                        "sha256_utf8": sha,
                        "lineno": getattr(h, "lineno", None),
                        "col": getattr(h, "col_offset", None),
                        "kind": kind,
                        "type": etype_str,
                        "header": header,
                        "first_body_line": body0,
                        "narrowing_suggestions": suggestions if (kind == "Exception") else [],
                    })

            elif isinstance(node, ast.Call):
                # dyn imports: __import__(...), *.import_module(...)
                func = node.func
                is_builtin_import = isinstance(func, ast.Name) and func.id == "__import__"
                is_import_module = isinstance(func, ast.Attribute) and func.attr == "import_module"
                if is_builtin_import or is_import_module:
                    arg0 = None
                    if node.args:
                        a = node.args[0]
                        if isinstance(a, ast.Constant) and isinstance(a.value, str):
                            arg0 = a.value

                    out["counts"]["dyn_import_calls"] += 1
                    per_file_counts[fkey]["dyn"] += 1

                    out["dyn_imports"].append({
                        "file": fkey,
                        "lineno": getattr(node, "lineno", None),
                        "func": "__import__" if is_builtin_import else _unparse(func),
                        "arg0": arg0,
                        "dynamic": arg0 is None,
                    })

    # top files by total interesting sites
    scored = []
    for f, c in per_file_counts.items():
        total = c["bare"] + c["Exception"] + c["BaseException"] + c["other"] + c["dyn"]
        if total:
            scored.append((total, f, c))
    scored.sort(reverse=True)
    out["top_files"] = [
        {"file": f, "score": total, "breakdown": c}
        for (total, f, c) in scored[:30]
    ]

    return out


def write_reports(result: Dict[str, Any], outdir: Path) -> Tuple[Path, Path]:
    _safe_mkdir(outdir)
    json_path = outdir / "EXCEPT_LANDSCAPE.json"
    txt_path = outdir / "EXCEPT_LANDSCAPE.txt"

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("EXCEPT LANDSCAPE REPORT (encoding-safe via tokenize.open)")
    lines.append("=" * 72)
    lines.append(f"root: {result['root']}")
    lines.append(f"files_total: {result['files_total']}")
    lines.append(f"files_scanned: {result['files_scanned']}")
    lines.append("")
    lines.append("COUNTS")
    lines.append("-" * 72)
    for k, v in result["counts"].items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("TOP FILES (by score)")
    lines.append("-" * 72)
    for row in result.get("top_files", []):
        b = row["breakdown"]
        lines.append(f"{row['score']:>4}  {row['file']}")
        lines.append(f"      bare={b['bare']}  Exception={b['Exception']}  BaseException={b['BaseException']}  other={b['other']}  dyn={b['dyn']}")
    lines.append("")
    lines.append("NOTES")
    lines.append("-" * 72)
    lines.append("This tool does NOT modify code. It only maps broad-excepts and dynamic imports.")
    lines.append("Narrowing suggestions are heuristic and must be applied manually/codemod in a later wave.")
    lines.append("Encoding safety: uses tokenize.open (PEP 263). No decode(errors='replace').")

    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="synapse", help="Root package dir to scan (default: synapse)")
    ap.add_argument("--out", default=None, help="Output dir (default: artifacts/EXCEPT_LANDSCAPE_<stamp>)")
    ap.add_argument("--exclude", default=None, help="Comma-separated dir names to exclude")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[FATAL] root not found: {root}", file=sys.stderr)
        return 2

    exclude = set(EXCLUDE_DIRS_DEFAULT)
    if args.exclude:
        for x in args.exclude.split(","):
            x = x.strip()
            if x:
                exclude.add(x)

    stamp = os.environ.get("SYNAPSE_STAMP")
    if not stamp:
        stamp = "run"
    outdir = Path(args.out) if args.out else Path("artifacts") / f"EXCEPT_LANDSCAPE_{stamp}"
    outdir = outdir.resolve()

    result = analyze(root, exclude)
    json_path, txt_path = write_reports(result, outdir)

    # stdout summary (single-line friendly)
    c = result["counts"]
    print(f"OK outdir={outdir}")
    print(f"counts bare={c['bare_except']} exc_Exception={c['except_Exception']} exc_BaseException={c['except_BaseException']} exc_other={c['except_other']} dyn_import_calls={c['dyn_import_calls']}")
    print(f"json={json_path}")
    print(f"txt={txt_path}")
    print(f"read_errors={len(result['read_errors'])} syntax_errors={len(result['syntax_errors'])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
