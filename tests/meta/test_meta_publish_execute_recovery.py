"""Regression tests for permanent retirement of legacy Meta live execution."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import synapse.meta_publish_execute as mpe


def test_live_recovery_flags_fail_closed_without_reading_malformed_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = tmp_path / "malformed-plan.json"
    original = "{this is deliberately invalid json"
    plan.write_text(original, encoding="utf-8")
    out = tmp_path / "out.json"
    history = tmp_path / "history"

    rc = mpe.main(
        [
            "--mode",
            "live",
            "--plan",
            str(plan),
            "--out",
            str(out),
            "--out-dir",
            str(history),
            "--continue-on-error",
            "--ledger-disable",
        ]
    )

    diagnostic = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert diagnostic["diagnostic"] == "LEGACY_META_LIVE_PERMANENTLY_DISABLED"
    assert plan.read_text(encoding="utf-8") == original
    assert not out.exists()
    assert not history.exists()


def test_live_disabled_helper_has_no_transport_injection_surface() -> None:
    assert str(mpe.LEGACY_META_LIVE_PERMANENTLY_DISABLED) == (
        "LEGACY_META_LIVE_PERMANENTLY_DISABLED"
    )

    parameters = list(inspect.signature(mpe._legacy_live_disabled).parameters)
    assert parameters == []
