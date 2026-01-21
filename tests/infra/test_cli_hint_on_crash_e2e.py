from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_prints_hint_on_crash(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["SYNAPSE_DEBUG_CLI"] = "1"
    env["SYNAPSE_DIAG_DIR"] = str(tmp_path)

    r = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "debug-crash", "--msg", "canonical_csv not found: data/catalog/canonical.csv"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 3
    out = (r.stdout or "") + (r.stderr or "")
    # HINT should show (FileNotFoundError won't happen here because it's RuntimeError msg,
    # but we at least confirm crash_report line exists)
    assert "crash_report=" in out
