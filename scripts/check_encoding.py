"""scripts/check_encoding.py
SYNAPSE — Encoding Guard
- Blocks UTF-8 BOM (EF BB BF)
- Validates UTF-8 decodability
marker: ENCODING_GUARD_2026-01-20_V2_DATA_IGNORED
"""

from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"

DEFAULT_PATTERNS = [
    "pytest.ini",
    "pyproject.toml",
    "**/*.py",
    "**/*.ps1",
    "**/*.json",
    "**/*.md",
    "**/*.html",
]

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "data",          # <- clave: outputs/generados (no los audites)
    "secrets",
}

def is_ignored(path: Path) -> bool:
    parts = set(path.parts)
    return any(d in parts for d in IGNORE_DIRS)

def check_file(p: Path):
    try:
        raw = p.read_bytes()
    except Exception as e:
        return False, f"read_error: {p} -> {e}"

    if raw.startswith(BOM):
        return False, f"bom_detected: {p}"

    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return False, f"invalid_utf8: {p} -> {e}"

    return True, ""

def main():
    repo = Path(__file__).resolve().parent.parent
    errors = []
    checked = 0

    for pat in DEFAULT_PATTERNS:
        for p in repo.glob(pat):
            if not p.is_file():
                continue
            if is_ignored(p):
                continue
            ok, msg = check_file(p)
            checked += 1
            if not ok:
                errors.append(msg)

    if errors:
        print("ENCODING GUARD: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"Checked: {checked} files", file=sys.stderr)
        return 1

    print(f"ENCODING GUARD: OK (checked {checked} files)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())