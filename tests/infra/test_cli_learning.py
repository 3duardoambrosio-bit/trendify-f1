from __future__ import annotations


def test_cli_learning_dry_run_no_heavy_imports() -> None:
    from synapse.cli.main import main  # noqa: WPS433
    import sys as _sys  # noqa: WPS433

    rc = main(["learning"])
    assert rc == 0
    assert "synapse.learning.learning_loop" not in _sys.modules


def test_cli_learning_explicit_dry_run_ok() -> None:
    from synapse.cli.main import main  # noqa: WPS433

    rc = main(["learning", "--dry-run"])
    assert rc == 0
