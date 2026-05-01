"""Regression tests for live-ledger safety in meta_publish_execute."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import synapse.infra.file_fingerprint as file_fingerprint
import synapse.infra.live_gate as live_gate
import synapse.infra.meta_publish_ledger as meta_publish_ledger
import synapse.infra.run_fingerprint as run_fingerprint
import synapse.meta_publish_execute as mpe


def _write_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "i": 1,
                        "key": "step-1",
                        "op": "create_campaign",
                        "endpoint": "/act_<META_AD_ACCOUNT_ID>/campaigns",
                        "payload": {"name": "Regression Campaign"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_live_ledger_disable_is_forbidden(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    out = tmp_path / "out.json"
    out_dir = tmp_path / "history"
    _write_plan(plan)

    with pytest.raises(RuntimeError, match="--ledger-disable is forbidden in --mode live"):
        mpe.main(
            [
                "--plan",
                str(plan),
                "--out",
                str(out),
                "--out-dir",
                str(out_dir),
                "--mode",
                "live",
                "--ledger-disable",
            ]
        )


def test_live_missing_created_id_returns_fail_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = tmp_path / "plan.json"
    out = tmp_path / "out.json"
    out_dir = tmp_path / "history"
    _write_plan(plan)

    monkeypatch.setenv("META_ACCESS_TOKEN", "token-test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "1234567890")

    monkeypatch.setattr(mpe, "_repo_root_from_plan", lambda _plan_path: tmp_path)
    monkeypatch.setattr(mpe, "_runtime_snapshot", lambda *args, **kwargs: {"mode": kwargs.get("mode", "live")})

    monkeypatch.setattr(
        file_fingerprint,
        "compute_file_fingerprints_from_steps",
        lambda steps, cwd: {"count": 0, "missing": 0, "entries": {}, "overall_sha12": "0" * 12},
    )
    monkeypatch.setattr(
        run_fingerprint,
        "compute_run_fingerprint",
        lambda plan_hash, runtime_snapshot: SimpleNamespace(
            fingerprint="f" * 64,
            fingerprint_12="f" * 12,
        ),
    )
    monkeypatch.setattr(
        live_gate,
        "check_meta_live_gate",
        lambda: SimpleNamespace(ok=True, status="OK", reason="passed", meta={}),
    )

    commit_calls: list[dict] = []

    class DummyLedger:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def reuse_or_raise_drift(self, **kwargs):
            return None

        def commit(self, **kwargs) -> None:
            commit_calls.append(kwargs)

    monkeypatch.setattr(meta_publish_ledger, "default_config", lambda path: {"path": str(path)})
    monkeypatch.setattr(meta_publish_ledger, "MetaPublishLedger", DummyLedger)
    monkeypatch.setattr(mpe, "_http_post", lambda url, data, access_token: {"ok": True})

    exit_code = mpe.main(
        [
            "--plan",
            str(plan),
            "--out",
            str(out),
            "--out-dir",
            str(out_dir),
            "--mode",
            "live",
        ]
    )

    assert exit_code == 2
    assert out.exists() is True

    run = json.loads(out.read_text(encoding="utf-8"))
    assert run["status"] == "FAIL"
    assert run["counts"]["errors"] == 1
    assert run["errors"][0]["error"] == "missing_created_id"
    assert run["results"][0]["status"] == "FAIL"
    assert run["results"][0]["error"] == "missing_created_id"
    assert commit_calls == []
