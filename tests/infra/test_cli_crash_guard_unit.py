from __future__ import annotations

import os
from pathlib import Path

import synapse.cli.main as cm


def test_cli_crash_guard_writes_report(tmp_path: Path, monkeypatch) -> None:
    # Force diagnostics to write to tmp dir
    monkeypatch.setenv("SYNAPSE_DIAG_DIR", str(tmp_path))

    # Monkeypatch build_parser to create a fake command that crashes
    import argparse

    def build_parser() -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog="synapse.cli")
        sub = p.add_subparsers(dest="command", required=True)
        c = sub.add_parser("boom")
        c.set_defaults(_fn=lambda _args: (_ for _ in ()).throw(RuntimeError("kaboom")))
        return p

    monkeypatch.setattr(cm, "build_parser", build_parser)

    rc = cm.main(["boom"])
    assert rc == 3

    reports = list(tmp_path.glob("error_*.json"))
    assert reports, "expected crash report file"
    txt = reports[0].read_text(encoding="utf-8")
    assert "kaboom" in txt
