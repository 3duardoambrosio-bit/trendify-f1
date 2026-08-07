from __future__ import annotations

import json
from pathlib import Path

import pytest

import synapse.meta_publish_execute as mpe


DISABLED_DIAGNOSTIC = "LEGACY_META_LIVE_PERMANENTLY_DISABLED"
OFFLINE_CONTRACT = {
    "offline_only": True,
    "external_write": False,
    "legacy_live_disabled": True,
}


def _write_plan(path: Path, steps: list[dict]) -> Path:
    plan = {
        "marker": "TEST_PLAN",
        "graph_version": "v25.0",
        "ad_account": "/<META_AD_ACCOUNT_ID>/campaigns",
        "plan_hash": "sha256:testplan",
        "steps": steps,
    }
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _assert_offline_contract(result: dict) -> None:
    for key, value in OFFLINE_CONTRACT.items():
        assert result[key] is value


def test_live_is_disabled_before_plan_env_runtime_or_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("live retirement guard was reached too late")

    monkeypatch.setattr(mpe, "_read_json", forbidden)
    monkeypatch.setattr(mpe, "_write_json", forbidden)
    monkeypatch.setattr(mpe, "_load_json_arg", forbidden)
    monkeypatch.setattr(mpe, "_repo_root_from_plan", forbidden)
    monkeypatch.setattr(mpe.os, "getenv", forbidden)

    plan = tmp_path / "plan-must-not-be-read.json"
    out = tmp_path / "run-must-not-exist.json"
    history = tmp_path / "history-must-not-exist"
    ledger = tmp_path / "ledger-must-not-exist"

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
            "--targeting-json",
            f"@{tmp_path / 'targeting-must-not-be-read.json'}",
            "--promoted-object-json",
            f"@{tmp_path / 'promoted-must-not-be-read.json'}",
            "--status",
            "ACTIVE",
            "--continue-on-error",
            "--ledger-dir",
            str(ledger),
            "--ledger-disable",
        ]
    )

    diagnostic = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert diagnostic["diagnostic"] == DISABLED_DIAGNOSTIC
    assert diagnostic["mode"] == "live"
    assert diagnostic["status"] == "FAIL"
    _assert_offline_contract(diagnostic)
    assert not plan.exists()
    assert not out.exists()
    assert not history.exists()
    assert not ledger.exists()


@pytest.mark.parametrize(
    "legacy_flags",
    [
        [],
        ["--continue-on-error"],
        ["--ledger-disable"],
        ["--continue-on-error", "--ledger-disable", "--status", "ACTIVE"],
    ],
)
def test_no_legacy_cli_or_environment_flags_reactivate_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    legacy_flags: list[str],
) -> None:
    for key in (
        "SYNAPSE_META_LIVE",
        "SYNAPSE_LIVE_META",
        "SYNAPSE_LIVE_WRITE",
        "META_LIVE_ENABLED",
    ):
        monkeypatch.setenv(key, "1")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")

    out = tmp_path / "must-not-exist.json"
    rc = mpe.main(
        [
            "--mode",
            "live",
            "--plan",
            str(tmp_path / "missing-plan.json"),
            "--out",
            str(out),
            *legacy_flags,
        ]
    )

    diagnostic = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert diagnostic["diagnostic"] == DISABLED_DIAGNOSTIC
    assert not out.exists()


def test_legacy_executor_has_no_http_transport_surface() -> None:
    source = Path(mpe.__file__).read_text(encoding="utf-8")

    assert not hasattr(mpe, "_http_post")
    assert not hasattr(mpe, "_http_post_multipart")
    for forbidden in (
        "urlopen",
        "_http_post(",
        "_http_post_multipart(",
        "graph.facebook.com",
        "META_ACCESS_TOKEN",
        "check_meta_live_gate",
        "MetaPublishLedger",
        "ledger.commit",
    ):
        assert forbidden not in source


def test_dry_mode_is_local_and_creates_no_result_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _write_plan(tmp_path / "plan.json", [])
    out = tmp_path / "run.json"
    history = tmp_path / "history"

    rc = mpe.main(
        [
            "--mode",
            "dry",
            "--plan",
            str(plan),
            "--out",
            str(out),
            "--out-dir",
            str(history),
        ]
    )

    stdout = capsys.readouterr().out
    assert rc == 0
    assert "offline_only=true" in stdout
    assert "external_write=false" in stdout
    assert "legacy_live_disabled=true" in stdout
    assert not out.exists()
    assert not history.exists()


def test_simulate_mode_generates_deterministic_offline_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("META_AD_ACCOUNT_ID", raising=False)
    plan = _write_plan(
        tmp_path / "plan.json",
        [
            {
                "i": 1,
                "op": "create_campaign",
                "key": "meta:campaign:test_campaign",
                "endpoint": "/<META_AD_ACCOUNT_ID>/campaigns",
                "depends_on": [],
                "payload": {
                    "name": "Campaign X",
                    "status": "PAUSED",
                },
            }
        ],
    )
    out = tmp_path / "run.json"
    history = tmp_path / "history"

    rc = mpe.main(
        [
            "--mode",
            "simulate",
            "--plan",
            str(plan),
            "--out",
            str(out),
            "--out-dir",
            str(history),
            "--ledger-disable",
            "--continue-on-error",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report = json.loads(out.read_text(encoding="utf-8"))
    expected_id = mpe._simulate_id("meta:campaign:test_campaign", "sha256:testplan")

    assert rc == 0
    assert report["status"] == "OK"
    assert report["counts"] == {"steps": 1, "results": 1, "errors": 0}
    assert report["ledger"]["enabled"] is False
    assert report["id_map"]["meta:campaign:test_campaign"] == expected_id
    assert report["results"][0]["simulated_id"] == expected_id
    assert "created_id" not in report["results"][0]
    assert "response" not in report["results"][0]
    _assert_offline_contract(report)
    _assert_offline_contract(report["results"][0])
    _assert_offline_contract(summary)
    assert len(list(history.glob("meta_publish_run_simulate_*.json"))) == 1
