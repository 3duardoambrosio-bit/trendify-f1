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


def test_live_missing_dependency_fails_before_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(
        tmp_path / "plan.json",
        [
            {
                "i": 1,
                "op": "create_adset",
                "key": "meta:adset:test_adset",
                "endpoint": "/<META_AD_ACCOUNT_ID>/adsets",
                "depends_on": ["meta:campaign:missing"],
                "payload": {"name": "Adset X"},
            }
        ],
    )
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(ok=True, status="OK", reason="passed"),
    ), patch("synapse.meta_publish_execute._http_post") as mock_post:
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
                "--ledger-dir", str(tmp_path / "ledger"),
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 2
    assert report["status"] == "FAIL"
    assert report["counts"]["results"] == 1
    assert report["counts"]["errors"] == 1
    assert "missing deps" in report["errors"][0]["error"]
    assert report["results"][0]["status"] == "FAIL"
    mock_post.assert_not_called()


def test_live_unresolved_placeholders_fail_before_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
                    "daily_budget": "<DAILY_BUDGET_MINOR_UNITS>",
                },
            }
        ],
    )
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(ok=True, status="OK", reason="passed"),
    ), patch("synapse.meta_publish_execute._http_post") as mock_post:
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
                "--ledger-dir", str(tmp_path / "ledger"),
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 2
    assert report["status"] == "FAIL"
    assert "unresolved placeholders" in report["errors"][0]["error"]
    assert "<DAILY_BUDGET_MINOR_UNITS>" in report["results"][0]["unresolved"]
    mock_post.assert_not_called()


def test_live_upload_video_source_without_file_ref_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(
        tmp_path / "plan.json",
        [
            {
                "i": 1,
                "op": "upload_video",
                "key": "meta:video:test_video",
                "endpoint": "/<META_AD_ACCOUNT_ID>/advideos",
                "depends_on": [],
                "payload": {
                    "name": "Video X",
                    "source": "not_a_file_ref",
                },
            }
        ],
    )
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(ok=True, status="OK", reason="passed"),
    ), patch("synapse.meta_publish_execute._http_post_multipart") as mock_multi:
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
                "--ledger-dir", str(tmp_path / "ledger"),
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 2
    assert report["status"] == "FAIL"
    assert "missing <FILE:...> source" in report["errors"][0]["error"]
    mock_multi.assert_not_called()


def test_live_success_create_campaign_sets_created_id_and_id_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(ok=True, status="OK", reason="passed"),
    ), patch(
        "synapse.meta_publish_execute._http_post",
        return_value={"id": "CAMP-123"},
    ) as mock_post:
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
                "--ledger-dir", str(tmp_path / "ledger"),
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["status"] == "OK"
    assert report["counts"]["results"] == 1
    assert report["counts"]["errors"] == 0
    assert report["results"][0]["created_id"] == "CAMP-123"
    assert report["results"][0]["endpoint_resolved"] == "/123456789/campaigns"
    assert report["id_map"]["meta:campaign:test_campaign"] == "CAMP-123"

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://graph.facebook.com/v25.0/123456789/campaigns"
    assert kwargs["access_token"] == "tok_test"
    assert kwargs["data"]["name"] == "Campaign X"
    assert kwargs["data"]["status"] == "PAUSED"


def test_live_upload_video_success_uses_multipart_and_maps_video_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake-video")
    plan = _write_plan(
        tmp_path / "plan.json",
        [
            {
                "i": 1,
                "op": "upload_video",
                "key": "meta:video:test_video",
                "endpoint": "/<META_AD_ACCOUNT_ID>/advideos",
                "depends_on": [],
                "payload": {
                    "name": "Video X",
                    "source": f"<FILE:{video_path}>",
                },
            }
        ],
    )
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(ok=True, status="OK", reason="passed"),
    ), patch(
        "synapse.meta_publish_execute._http_post_multipart",
        return_value={"video_id": "VID-123"},
    ) as mock_multi:
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
                "--ledger-dir", str(tmp_path / "ledger"),
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["status"] == "OK"
    assert report["results"][0]["created_id"] == "VID-123"
    assert report["id_map"]["meta:video:test_video"] == "VID-123"

    mock_multi.assert_called_once()
    args, kwargs = mock_multi.call_args
    assert args[0] == "https://graph.facebook.com/v25.0/123456789/advideos"
    assert kwargs["access_token"] == "tok_test"
    assert kwargs["file_path"] == video_path.resolve()
    assert kwargs["fields"]["name"] == "Video X"


def test_live_continue_on_error_keeps_next_step_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(
        tmp_path / "plan.json",
        [
            {
                "i": 1,
                "op": "create_campaign",
                "key": "meta:campaign:bad_campaign",
                "endpoint": "/<META_AD_ACCOUNT_ID>/campaigns",
                "depends_on": [],
                "payload": {
                    "name": "Bad Campaign",
                    "daily_budget": "<DAILY_BUDGET_MINOR_UNITS>",
                },
            },
            {
                "i": 2,
                "op": "create_campaign",
                "key": "meta:campaign:good_campaign",
                "endpoint": "/<META_AD_ACCOUNT_ID>/campaigns",
                "depends_on": [],
                "payload": {
                    "name": "Good Campaign",
                    "status": "PAUSED",
                },
            },
        ],
    )
    out = tmp_path / "run.json"
    hist = tmp_path / "runs"

    monkeypatch.setenv("META_ACCESS_TOKEN", "tok_test")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")

    p1, p2 = _patch_common(file_fps=_fake_file_fps())
    with p1, p2, patch(
        "synapse.infra.live_gate.check_meta_live_gate",
        return_value=_fake_gate(ok=True, status="OK", reason="passed"),
    ), patch(
        "synapse.meta_publish_execute._http_post",
        return_value={"id": "CAMP-200"},
    ) as mock_post:
        rc = mpe.main(
            [
                "--plan", str(plan),
                "--out", str(out),
                "--out-dir", str(hist),
                "--mode", "live",
                "--continue-on-error",
                "--ledger-dir", str(tmp_path / "ledger"),
            ]
        )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 2
    assert report["status"] == "FAIL"
    assert report["counts"]["results"] == 2
    assert report["counts"]["errors"] == 1
    assert report["results"][0]["status"] == "FAIL"
    assert report["results"][1]["status"] == "OK"
    assert report["results"][1]["created_id"] == "CAMP-200"
    assert report["id_map"]["meta:campaign:good_campaign"] == "CAMP-200"
    mock_post.assert_called_once()
