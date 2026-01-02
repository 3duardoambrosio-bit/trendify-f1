from __future__ import annotations

from synapse.infra.dry_run import resolve_dry_run


def test_resolve_apply_wins() -> None:
    d = resolve_dry_run(apply=True, dry_run_flag=True, default_dry_run=True)
    assert d.dry_run is False
    assert d.reason == "apply"


def test_resolve_explicit_dry_run() -> None:
    d = resolve_dry_run(apply=False, dry_run_flag=True, default_dry_run=False)
    assert d.dry_run is True
    assert d.reason == "explicit_dry_run"


def test_resolve_default() -> None:
    d = resolve_dry_run(apply=False, dry_run_flag=False, default_dry_run=True)
    assert d.dry_run is True
    assert d.reason == "default"
