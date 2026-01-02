from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse.legacy.legacy_cleanup import LegacyCleanupRunner


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_legacy_cleanup_generates_report(tmp_path: Path, monkeypatch):
    # Fake repo
    repo = tmp_path
    _write(repo / "synapse" / "__init__.py", "")
    _write(repo / "synapse" / "quality_gate.py", "x=1\n")
    _write(repo / "synapse" / "quality_gate_v2.py", "y=2\n")

    # Make it importable
    monkeypatch.syspath_prepend(str(repo))

    # Run
    r = LegacyCleanupRunner(repo)
    rep = r.run(dry_run=False, force=True)

    assert rep.schema_version == "1.0.0"
    assert (repo / "data" / "legacy" / "legacy_report_latest.md").exists()
    assert (repo / "data" / "legacy" / "legacy_report_latest.json").exists()
    assert any("quality_gate" in d for d in rep.duplicates)


def test_idempotency_uses_cached_report(tmp_path: Path, monkeypatch):
    repo = tmp_path
    _write(repo / "synapse" / "__init__.py", "")
    _write(repo / "synapse" / "quality_gate_v2.py", "y=2\n")
    monkeypatch.syspath_prepend(str(repo))

    r = LegacyCleanupRunner(repo)
    rep1 = r.run(dry_run=False, force=True)
    rep2 = r.run(dry_run=False, force=False)

    assert rep1.input_hash == rep2.input_hash


def test_dry_run_writes_md_but_not_json(tmp_path: Path, monkeypatch):
    repo = tmp_path
    _write(repo / "synapse" / "__init__.py", "")
    _write(repo / "synapse" / "quality_gate_v2.py", "y=2\n")
    monkeypatch.syspath_prepend(str(repo))

    r = LegacyCleanupRunner(repo)
    rep = r.run(dry_run=True, force=True)

    out_dir = repo / "data" / "legacy"
    assert (out_dir / "legacy_report_latest.md").exists()
    assert not (out_dir / "legacy_report_latest.json").exists()
