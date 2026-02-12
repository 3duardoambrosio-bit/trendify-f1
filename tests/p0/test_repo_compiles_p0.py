from __future__ import annotations

from pathlib import Path
import py_compile

EXCLUDE_SUBSTR = (
    "/.git/",
    "/.venv/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/node_modules/",
)

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _norm(p: Path) -> str:
    return str(p).replace("\\", "/")

def test_repo_compiles_no_syntax_errors() -> None:
    root = _repo_root()
    offenders: list[str] = []

    for p in root.rglob("*.py"):
        s = _norm(p)
        if any(x in s for x in EXCLUDE_SUBSTR):
            continue
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception:
            offenders.append(s)

    assert offenders == [], f"SYNTAX_ERRORS_DETECTED count={len(offenders)} offenders={offenders}"
