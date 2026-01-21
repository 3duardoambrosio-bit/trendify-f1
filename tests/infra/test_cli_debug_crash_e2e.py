from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_debug_crash_creates_report(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["SYNAPSE_DEBUG_CLI"] = "1"
    env["SYNAPSE_DIAG_DIR"] = str(tmp_path)

    r = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "debug-crash", "--msg", "hello-crash"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 3, (r.stdout, r.stderr)

    reports = list(tmp_path.glob("error_*.json"))
    assert reports
    txt = reports[0].read_text(encoding="utf-8")
    assert "hello-crash" in txt
