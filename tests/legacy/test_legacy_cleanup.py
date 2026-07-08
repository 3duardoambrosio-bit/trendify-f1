from __future__ import annotations

import json
from pathlib import Path

from synapse.ledger_ndjson import read_events
from synapse.legacy import legacy_cleanup as lc


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _targets() -> list[lc.LegacyTarget]:
    return [
        lc.LegacyTarget(
            module="tempmods.quality_gate",
            rel_path="tempmods/quality_gate.py",
            role="Legacy quality gate v1",
            replacement_hint="Use tempmods.quality_gate_v2",
            action="DELETE_AFTER_MIGRATION",
        ),
        lc.LegacyTarget(
            module="tempmods.quality_gate_v2",
            rel_path="tempmods/quality_gate_v2.py",
            role="Quality gate v2",
            replacement_hint="Current default",
            action="KEEP",
        ),
    ]


def _prepare_repo(repo: Path) -> None:
    _write(repo / "tempmods" / "__init__.py", "")
    _write(repo / "tempmods" / "quality_gate.py", "x = 1\n")
    _write(repo / "tempmods" / "quality_gate_v2.py", "y = 2\n")


def test_legacy_cleanup_generates_report(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _prepare_repo(repo)

    monkeypatch.syspath_prepend(str(repo))
    monkeypatch.setattr(lc, "LEGACY_TARGETS", _targets())

    runner = lc.LegacyCleanupRunner(repo)
    rep = runner.run(force=True)

    assert rep.schema_version == "1.0.0"
    assert len(rep.modules) == 2
    assert (repo / "data" / "legacy" / "legacy_report_latest.json").exists()
    assert (repo / "data" / "legacy" / "legacy_report_latest.md").exists()
    assert (repo / "data" / "legacy" / "legacy_state.json").exists()


def test_legacy_cleanup_uses_cached_report_when_input_hash_matches(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _prepare_repo(repo)

    monkeypatch.syspath_prepend(str(repo))
    monkeypatch.setattr(lc, "LEGACY_TARGETS", _targets())

    runner = lc.LegacyCleanupRunner(repo)
    _ = runner.run(force=True)

    report_json = repo / "data" / "legacy" / "legacy_report_latest.json"
    cached = json.loads(report_json.read_text(encoding="utf-8"))
    cached["schema_version"] = "cached-version"
    report_json.write_text(json.dumps(cached, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rep2 = runner.run(force=False)
    assert rep2.schema_version == "cached-version"


def test_legacy_cleanup_writes_canonical_ledger_event(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _prepare_repo(repo)

    monkeypatch.syspath_prepend(str(repo))
    monkeypatch.setattr(lc, "LEGACY_TARGETS", _targets())

    runner = lc.LegacyCleanupRunner(repo)
    _ = runner.run(force=True)

    ledger_path = repo / "runtime" / "ledger" / "events.ndjson"
    assert ledger_path.exists()

    rows = read_events(ledger_path)
    assert any(
        r.get("event_type") == "LEGACY_CLEANUP_REPORTED"
        and r.get("entity_id") == "legacy_cleanup"
        for r in rows
    )