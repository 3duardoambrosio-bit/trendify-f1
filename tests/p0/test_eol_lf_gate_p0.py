from __future__ import annotations

import subprocess
from pathlib import Path

# Gate ultra-específico: archivos críticos que ya tocaron EOL.
CRITICAL_PATHS = (
    ".gitattributes",
    ".gitignore",
    ".github/workflows/f1.yml",
    "ops/dropi_dump_ingest.py",
    "synapse/meta_auth_check.py",
    "synapse/creative_assets_build.py",
    "tests/p0/test_repo_compiles_p0.py",
    "tests/p0/test_eol_lf_gate_p0.py",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

def test_critical_files_are_lf_in_index_and_worktree() -> None:
    root = _repo_root()

    # Ejecuta: git ls-files --eol -- <paths>
    cmd = ["git", "ls-files", "--eol", "--", *CRITICAL_PATHS]
    try:
        out = subprocess.check_output(cmd, cwd=str(root), text=True, stderr=subprocess.STDOUT)
    except FileNotFoundError as e:
        raise AssertionError("GIT_NOT_FOUND: 'git' no está en PATH; no puedo correr gate eol") from e
    except subprocess.CalledProcessError as e:
        raise AssertionError(f"GIT_EOLOPTS_FAILED exit={e.returncode} out={e.output!r}") from e

    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    # Aceptación numérica: deben salir exactamente N líneas
    assert len(lines) == len(CRITICAL_PATHS), f"EOL_GATE_MISSING_FILES expected={len(CRITICAL_PATHS)} got={len(lines)} lines={lines}"

    offenders: list[str] = []
    for ln in lines:
        # Esperamos tokens como: "i/lf    w/lf    attr/text eol=lf        path"
        if "i/lf" not in ln or "w/lf" not in ln:
            offenders.append(ln)

    assert offenders == [], f"EOL_NOT_LF offenders_count={len(offenders)} offenders={offenders}"
