from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_forecast_suite_rejects_relative_outdir_outside_root(tmp_path):
    root = Path(__file__).resolve().parents[2]
    tools_dir = root / "tools"

    cmd = [
        sys.executable,
        str(root / "tools" / "synapse_forecast_suite.py"),
        "--outdir",
        "../out/forecast",
        "--labels",
        "FINISHED_BASE,FINISHED_AGGRESSIVE",
        "--months",
        "36",
    ]
    p = subprocess.run(cmd, cwd=str(tools_dir), capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")

    assert p.returncode == 2, out
    assert "SUITE_OK=0" in out
    assert "BAD_GATE outdir_within_root=0" in out
