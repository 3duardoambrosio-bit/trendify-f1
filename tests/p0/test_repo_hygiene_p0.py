from __future__ import annotations

from pathlib import Path

from synapse.infra.repo_hygiene import scan_repo_hygiene


def test_repo_hygiene_no_staging_py_and_no_session_dirs():
    repo = Path(__file__).resolve().parents[2]
    r = scan_repo_hygiene(str(repo))
    assert r.ok is True, f"errors={r.errors} findings={r.findings}"


def test_pytest_ini_ignores_claude_worktrees():
    repo = Path(__file__).resolve().parents[2]
    ini = (repo / "pytest.ini").read_text(encoding="utf-8")
    assert "norecursedirs" in ini
    assert ".claude" in ini, "pytest.ini must ignore .claude worktrees (prevents ImportPathMismatch)"
