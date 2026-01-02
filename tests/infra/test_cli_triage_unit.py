from __future__ import annotations

from pathlib import Path

from synapse.infra.diagnostics import capture_exception
import synapse.cli.main as cm


def test_cli_triage_lists_latest(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SYNAPSE_DIAG_DIR", str(tmp_path))

    try:
        raise RuntimeError("kaboom-triage")
    except RuntimeError as e:
        capture_exception(e, diag_dir=tmp_path)

    rc = cm.main(["triage", "--last"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "kaboom-triage" in out
    assert "triage: fingerprint=" in out
