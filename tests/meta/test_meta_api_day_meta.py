from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

import synapse.meta_api_day_meta as api_day
import synapse.meta_publish_execute as execute
import synapse.meta_publish_preflight as preflight


DISABLED_DIAGNOSTIC = "LEGACY_META_LIVE_PERMANENTLY_DISABLED"
OFFLINE_CONTRACT = {
    "offline_only": True,
    "external_write": False,
    "legacy_live_disabled": True,
}


def _assert_offline_contract(result: dict) -> None:
    for key, value in OFFLINE_CONTRACT.items():
        assert result[key] is value


def _argv_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_explicit_live_blocks_before_secrets_plan_outputs_or_delegation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("live retirement guard was reached too late")

    monkeypatch.setattr(api_day, "_load_secrets_from_dir", forbidden)
    monkeypatch.setattr(api_day, "_read_json", forbidden)
    monkeypatch.setattr(preflight, "main", forbidden)
    monkeypatch.setattr(execute, "main", forbidden)

    for key in (
        "SYNAPSE_META_LIVE",
        "SYNAPSE_LIVE_META",
        "SYNAPSE_LIVE_WRITE",
        "META_LIVE_ENABLED",
    ):
        monkeypatch.setenv(key, "1")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")

    plan = tmp_path / "plan-must-not-be-read.json"
    secrets = tmp_path / "secrets-must-not-be-read"
    out_preflight = tmp_path / "preflight-must-not-exist.json"
    out_run = tmp_path / "run-must-not-exist.json"
    ledger = tmp_path / "ledger-must-not-exist"

    rc = api_day.main(
        [
            "--mode",
            "live",
            "--plan",
            str(plan),
            "--out-preflight",
            str(out_preflight),
            "--out-run",
            str(out_run),
            "--load-secrets",
            "--print-secrets-sanity",
            "--secrets-dir",
            str(secrets),
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
    assert not secrets.exists()
    assert not out_preflight.exists()
    assert not out_run.exists()
    assert not ledger.exists()


def test_default_mode_delegates_only_to_local_simulate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, list[str]] = {}
    out_preflight = tmp_path / "preflight.json"
    out_run = tmp_path / "run.json"

    def fake_preflight(argv: list[str]) -> int:
        calls["preflight"] = list(argv)
        Path(_argv_value(argv, "--out")).write_text(
            json.dumps({"run_fingerprint_12": "offline-fp"}),
            encoding="utf-8",
        )
        return 0

    def fake_execute(argv: list[str]) -> int:
        calls["execute"] = list(argv)
        Path(_argv_value(argv, "--out")).write_text(
            json.dumps(
                {
                    "run_fingerprint_12": "offline-fp",
                    **OFFLINE_CONTRACT,
                }
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(preflight, "main", fake_preflight)
    monkeypatch.setattr(execute, "main", fake_execute)

    rc = api_day.main(
        [
            "--plan",
            str(tmp_path / "local-plan.json"),
            "--out-preflight",
            str(out_preflight),
            "--out-run",
            str(out_run),
            "--ledger-dir",
            str(tmp_path / "ledger"),
        ]
    )

    final_result = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert _argv_value(calls["preflight"], "--mode") == "simulate"
    assert _argv_value(calls["execute"], "--mode") == "simulate"
    assert final_result["mode"] == "simulate"
    assert final_result["fingerprint_match"] is True
    _assert_offline_contract(final_result)


def test_simulate_preflight_failure_reports_offline_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(preflight, "main", lambda _argv: 2)

    rc = api_day.main(
        [
            "--mode",
            "simulate",
            "--plan",
            str(tmp_path / "local-plan.json"),
            "--out-preflight",
            str(tmp_path / "preflight.json"),
            "--out-run",
            str(tmp_path / "run.json"),
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert result["stage"] == "preflight"
    assert result["status"] == "FAIL"
    _assert_offline_contract(result)


def test_local_secret_status_exposes_only_loaded_and_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_values = {
        "meta_access_token.txt": "Q7ZX_ACCESS_CREDENTIAL_ALPHA_91KM",
        "meta_ad_account_id.txt": "act_839104728561",
        "meta_page_id.txt": "P8VW_PAGE_CREDENTIAL_BETA_42JL",
        "meta_ig_actor_id.txt": "N6RT_ACTOR_CREDENTIAL_GAMMA_53HX",
    }
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    for filename, value in secret_values.items():
        (secrets_dir / filename).write_text(value, encoding="utf-8")

    shared_env: dict[str, str] = {}
    monkeypatch.setattr(
        api_day,
        "os",
        SimpleNamespace(environ=shared_env),
        raising=False,
    )
    monkeypatch.setattr(
        preflight,
        "os",
        SimpleNamespace(getenv=lambda key, default=None: shared_env.get(key, default)),
    )
    monkeypatch.setattr(
        execute,
        "os",
        SimpleNamespace(getenv=lambda key, default=None: shared_env.get(key, default)),
    )

    real_execute_main = execute.main
    history_dir = tmp_path / "history"

    def execute_under_temp(argv: list[str]) -> int:
        return real_execute_main([*argv, "--out-dir", str(history_dir)])

    monkeypatch.setattr(execute, "main", execute_under_temp)

    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "marker": "SECRET_BOUNDARY_TEST_PLAN",
                "graph_version": "v25.0",
                "plan_hash": "sha256:secret-boundary-test-plan",
                "steps": [
                    {
                        "i": 1,
                        "op": "create_campaign",
                        "key": "meta:campaign:secret_boundary",
                        "endpoint": "/<META_AD_ACCOUNT_ID>/campaigns",
                        "depends_on": [],
                        "payload": {"name": "Local simulation", "status": "PAUSED"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out_preflight = tmp_path / "preflight.json"
    out_run = tmp_path / "run.json"
    rc = api_day.main(
        [
            "--mode",
            "simulate",
            "--load-secrets",
            "--print-secrets-sanity",
            "--secrets-dir",
            str(secrets_dir),
            "--plan",
            str(plan),
            "--out-preflight",
            str(out_preflight),
            "--out-run",
            str(out_run),
        ]
    )

    captured = capsys.readouterr()
    decoder = json.JSONDecoder()
    records: list[dict] = []
    cursor = 0
    while cursor < len(captured.out):
        cursor += len(captured.out[cursor:]) - len(captured.out[cursor:].lstrip())
        if cursor >= len(captured.out):
            break
        record, cursor = decoder.raw_decode(captured.out, cursor)
        records.append(record)

    assert rc == 0
    assert captured.err == ""
    assert len(records) == 4
    sanity = records[0]
    assert sanity["stage"] == "secrets_sanity"
    assert sanity["no_secrets_printed"] is True
    _assert_offline_contract(sanity)

    assert set(sanity) == {
        "external_write",
        "legacy_live_disabled",
        "marker",
        "no_secrets_printed",
        "offline_only",
        "secret_loaded",
        "secret_source",
        "stage",
    }
    assert sanity["secret_loaded"] is True
    assert sanity["secret_source"] == "local_secret_files"
    assert api_day._secret_status({}) == {
        "secret_loaded": False,
        "secret_source": "local_secret_files",
    }
    assert shared_env == {}

    output_files = [
        out_preflight,
        out_run,
        *history_dir.glob("meta_publish_run_simulate_*.json"),
    ]
    assert len(output_files) == 3
    local_results = [path.read_text(encoding="utf-8") for path in output_files]
    serialized_results = json.dumps(records, ensure_ascii=False, sort_keys=True)
    combined_output = "\n".join(
        (captured.out, captured.err, serialized_results, *local_results)
    )
    derived_values: set[str] = set()
    for raw_value in secret_values.values():
        normalized_value = raw_value.removeprefix("act_")
        for value in (raw_value, normalized_value):
            derived_values.update(
                {
                    value,
                    value[:4],
                    value[-4:],
                    value[:8],
                    value[-8:],
                    quote(value, safe=""),
                    hashlib.sha256(value.encode("utf-8")).hexdigest(),
                    hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
                    hashlib.sha256(value.encode("utf-8")).hexdigest()[-12:],
                }
            )

    assert all(value not in combined_output for value in derived_values)
    preflight_result = json.loads(out_preflight.read_text(encoding="utf-8"))
    run_result = json.loads(out_run.read_text(encoding="utf-8"))
    assert preflight_result["runtime_snapshot"]["meta_ad_account_id"] == ""
    assert run_result["runtime_snapshot"]["meta_ad_account_id"] == ""
    assert preflight_result["per_step"][0]["endpoint_resolved"] == (
        "/<META_AD_ACCOUNT_ID>/campaigns"
    )
    assert run_result["results"][0]["endpoint_resolved"] == (
        "/<META_AD_ACCOUNT_ID>/campaigns"
    )


def test_live_guard_precedes_all_sensitive_or_side_effecting_operations() -> None:
    source = inspect.getsource(api_day.main)
    guard_position = source.index('if mode == "live":')

    for later_operation in (
        "if args.load_secrets:",
        "_load_secrets_from_dir(",
        "preflight_main(",
        "execute_main(",
        "_read_json(",
    ):
        assert guard_position < source.index(later_operation)

    assert "check_meta_live_gate" not in source
