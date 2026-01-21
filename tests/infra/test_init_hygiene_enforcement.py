from __future__ import annotations

import subprocess
import sys


def test_cli_help_no_runpy_warning() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "runpy" not in (r.stderr or "").lower()


def test_imports_do_not_pull_heavy_modules() -> None:
    import sys as _sys  # noqa: WPS433

    # controlled imports
    import synapse.cli  # noqa: F401
    import synapse.infra.dry_run  # noqa: F401
    import synapse.infra.contract_snapshot  # noqa: F401
    import synapse.infra.logging_std  # noqa: F401

    forbidden = [
        "synapse.infra.doctor",
        "synapse.pulse.market_pulse",
        "synapse.learning.learning_loop",
        "synapse.marketing_os.wave_runner",
    ]
    for m in forbidden:
        assert m not in _sys.modules, f"Init hygiene violated: {m} loaded"
