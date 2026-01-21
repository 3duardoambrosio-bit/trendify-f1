from __future__ import annotations

from synapse.cli.main import main


def test_cli_doctor_runs_green() -> None:
    rc = main(["doctor"])
    assert rc == 0
