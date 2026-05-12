from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BYPASS_FLAG = "-" * 2 + "no" + "-" + "verify"

POLICY_SURFACE_FILES = (
    "AGENTS.md",
    "docs/ops/A8_R43B_NO_VERIFY_POLICY.md",
    "tests/meta/test_no_verify_policy.py",
    "tools/a8_no_verify_policy_check.py",
)


def test_commit_hook_bypass_policy_surface_has_no_literal() -> None:
    offenders: list[str] = []

    for rel_path in POLICY_SURFACE_FILES:
        path = ROOT / rel_path
        assert path.exists(), rel_path
        text = path.read_text(encoding="utf-8")

        for line_no, line in enumerate(text.splitlines(), start=1):
            if BYPASS_FLAG in line:
                offenders.append(f"{rel_path}:{line_no}:{line.strip()}")

    assert offenders == []


def test_direct_policy_checker_exists() -> None:
    checker = ROOT / "tools/a8_no_verify_policy_check.py"
    assert checker.exists()

    text = checker.read_text(encoding="utf-8")
    assert BYPASS_FLAG not in text
    assert '"grep"' in text
    assert "timeout=20" in text
