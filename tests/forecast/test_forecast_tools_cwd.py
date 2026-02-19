from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_forecast_suite_runs_from_tools_cwd(tmp_path):
    """
    Regression: tools must be runnable even if current working directory is /tools.
    This catches accidental reintroduction of CWD-dependent pathing.
    """
    root = Path(__file__).resolve().parents[2]
    tools_dir = root / "tools"
    outdir = tmp_path / "forecast_out"

    cmd = [
        sys.executable,
        str(root / "tools" / "synapse_forecast_suite.py"),
        "--outdir",
        str(outdir),
        "--labels",
        "FINISHED_BASE,FINISHED_AGGRESSIVE",
        "--months",
        "36",
    ]
    p = subprocess.run(cmd, cwd=str(tools_dir), capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")

    assert p.returncode == 0, out
    assert "SUITE_OK=1" in out
    assert (outdir / "synapse_forecast_suite_report.json").exists()
