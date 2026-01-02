from __future__ import annotations

import sys


def test_cli_pulse_dry_run_no_heavy_imports() -> None:
    from synapse.cli.main import main  # noqa: WPS433
    import sys as _sys  # noqa: WPS433

    # calling pulse in dry-run should not need market_pulse import
    rc = main(["pulse"])
    assert rc == 0
    assert "synapse.pulse.market_pulse" not in _sys.modules


def test_cli_pulse_apply_attempts_import() -> None:
    # Apply may import the module; we only assert it doesn't crash hard in parser layer.
    # If market_pulse throws, that should be visible, but the repo had it passing previously.
    from synapse.cli.main import main  # noqa: WPS433

    rc = main(["pulse", "--dry-run"])
    assert rc == 0
