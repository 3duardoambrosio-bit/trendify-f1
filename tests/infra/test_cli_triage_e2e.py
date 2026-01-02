from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_triage_e2e(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["SYNAPSE_DEBUG_CLI"] = "1"
    env["SYNAPSE_DIAG_DIR"] = str(tmp_path)

    r1 = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "debug-crash", "--msg", "kaboom-e2e"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r1.returncode == 3, (r1.stdout, r1.stderr)

    r2 = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "triage", "--last"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r2.returncode == 0, (r2.stdout, r2.stderr)
    assert "kaboom-e2e" in (r2.stdout or "")
    assert "triage: top_frames:" in (r2.stdout or "")
