from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import synapse.meta_publish_execute as mpe


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


def _fake_file_fps(*, missing: int = 0, entries: dict | None = None) -> dict:
    return {
        "algo": "sha256",
        "count": 0,
        "missing": missing,
        "overall_sha12": "abc123def456",
        "overall_sha256": "0" * 64,
        "entries": entries or {},
    }


def _fake_run_fp() -> SimpleNamespace:
    return SimpleNamespace(
        fingerprint="fp_" + ("a" * 60),
        fingerprint_12="fp12abc12345",
    )


def _fake_gate(*, ok: bool, status: str, reason: str, meta: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        ok=ok,
        status=status,
        reason=reason,
        meta=meta or {},
    )


def _patch_common(*, file_fps: dict):
    return (
        patch(
            "synapse.infra.file_fingerprint.compute_file_fingerprints_from_steps",
            return_value=file_fps,
        ),
        patch(
            "synapse.infra.run_fingerprint.compute_run_fingerprint",
            return_value=_fake_run_fp(),
        ),
    )


def test_live_gate_not_ok_returns_skip_report(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [])
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(
            ok=False,
            status="SKIP",
            reason="meta_secrets_missing",
            meta={"scope": "meta"},
        ),
    ):
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["status"] == "SKIP"
    assert report["gate"]["reason"] == "meta_secrets_missing"
    assert report["counts"]["results"] == 0
    assert report["counts"]["errors"] == 0


def test_live_gate_ok_with_missing_files_returns_fail_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(tmp_path / "plan.json", [])
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    missing_path = str(tmp_path / "missing_video.mp4")
    file_fps = _fake_file_fps(
        missing=1,
        entries={missing_path: {"missing": True}},
    )

    p1, p2 = _patch_common(file_fps=file_fps)
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(
            ok=True,
            status="OK",
            reason="passed",
            meta={},
        ),
    ):
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 2
    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "missing_files"
    assert missing_path in report["errors"][0]["missing"]


def test_live_requires_meta_access_token_after_gate_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(tmp_path / "plan.json", [])
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(
            ok=True,
            status="OK",
            reason="passed",
            meta={},
        ),
    ):
        with pytest.raises(RuntimeError, match="META_ACCESS_TOKEN"):
            mpe.main(
                [
                    "--plan", str(plan),
                    "--out", str(out),
                    "--out-dir", str(hist),
                    "--mode", "live",
                ]
            )


def test_live_requires_meta_ad_account_id_after_gate_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(tmp_path / "plan.json", [])
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.delenv("META_AD_ACCOUNT_ID", raising=False)

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(
            ok=True,
            status="OK",
            reason="passed",
            meta={},
        ),
    ):
        with pytest.raises(RuntimeError, match="META_AD_ACCOUNT_ID"):
            mpe.main(
                [
                    "--plan", str(plan),
                    "--out", str(out),
                    "--out-dir", str(hist),
                    "--mode", "live",
                ]
            )


def test_simulate_mode_generates_deterministic_sim_ids(tmp_path: Path) -> None:
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
    hist = tmp_path / "runs"

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2:
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "simulate",
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["status"] == "OK"
    assert report["counts"]["results"] == 1
    sim_id = report["results"][0]["simulated_id"]
    assert sim_id.startswith("SIMCAMP_")
    assert report["id_map"]["meta:campaign:test_campaign"] == sim_id
