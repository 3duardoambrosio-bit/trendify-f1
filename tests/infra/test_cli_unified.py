from __future__ import annotations

import subprocess
import sys


def test_cli_help_lists_commands() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    out = (r.stdout or "") + (r.stderr or "")
    assert "doctor" in out
    assert "wave" in out
    assert "learning" in out
    assert "pulse" in out


def test_cli_import_hygiene_no_heavy_imports() -> None:
    import sys as _sys  # noqa: WPS433

    import synapse.cli  # noqa: F401

    # Must NOT be imported just by importing synapse.cli
    forbidden = [
        "synapse.infra.doctor",
        "synapse.pulse.market_pulse",
        "synapse.learning.learning_loop",
        "synapse.marketing_os.wave_runner",
    ]
    for m in forbidden:
        assert m not in _sys.modules, f"Import hygiene violated: {m} loaded"
