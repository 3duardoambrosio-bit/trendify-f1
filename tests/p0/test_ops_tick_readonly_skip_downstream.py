from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.ops_tick import (
    StepResult,
    TickConfig,
    _compute_status,
    _execute_steps,
    _parse_tick_config,
)


def _mk_fake_run(
    *,
    runner_rc: int = 0,
    runner_status: str = "COMPLETED",
    post_learning_rc: int = 0,
):
    calls: list[dict[str, object]] = []

    def _fake_run(cmd, env_overrides=None):
        cmd_text = " ".join(cmd)
        rc = 0
        stdout = ""
        if "synapse.runner" in cmd_text:
            rc = runner_rc
            stdout = f"LEARNING_STATUS={runner_status}\nLEARNING_RC={runner_rc}"
        elif "synapse.post_learning" in cmd_text:
            rc = post_learning_rc

        calls.append(
            {
                "cmd": cmd_text,
                "env": dict(env_overrides or {}),
            }
        )
        return StepResult(
            cmd=cmd_text,
            returncode=rc,
            stdout_tail=stdout,
            stderr_tail="",
        )

    return calls, _fake_run


def _config(
    *,
    no_import: bool,
    readonly: bool,
    prune: bool = False,
) -> TickConfig:
    return TickConfig(
        csv="auto",
        platform="meta",
        product_id="34357",
        prune=prune,
        no_import=no_import,
        effective_readonly=readonly,
    )


def test_execute_steps_no_import_readonly_skips_learning_and_downstream(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls, fake_run = _mk_fake_run()
    monkeypatch.chdir(tmp_path)

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        steps = _execute_steps(_config(no_import=True, readonly=True))

    commands = [str(call["cmd"]) for call in calls]
    step_commands = [step.cmd for step in steps]
    assert any("synapse.ledger_ndjson validate" in command for command in commands)
    assert not any("synapse.runner" in command for command in commands)
    assert not any("synapse.post_learning" in command for command in commands)
    assert not any("synapse.creative_queue" in command for command in commands)
    assert not any("synapse.creative_briefs" in command for command in commands)
    assert "<SKIP> synapse.runner --apply" in step_commands
    assert "<SKIP> synapse.post_learning" in step_commands
    assert "<SKIP> synapse.creative_queue" in step_commands
    assert "<SKIP> synapse.creative_briefs" in step_commands
    assert all(call["env"] == {"SYNAPSE_READONLY": "1"} for call in calls)
    assert list(tmp_path.rglob("*")) == []


def test_execute_steps_readonly_with_import_never_invokes_learning_or_downstream(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls, fake_run = _mk_fake_run()
    monkeypatch.chdir(tmp_path)

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        _execute_steps(_config(no_import=False, readonly=True))

    commands = [str(call["cmd"]) for call in calls]
    assert any("synapse.ad_results_import" in command for command in commands)
    assert not any("synapse.runner" in command for command in commands)
    assert not any("synapse.post_learning" in command for command in commands)
    assert not any("synapse.creative_queue" in command for command in commands)
    assert not any("synapse.creative_briefs" in command for command in commands)
    assert all(call["env"] == {"SYNAPSE_READONLY": "1"} for call in calls)
    assert list(tmp_path.rglob("*")) == []


def test_execute_steps_readonly_never_runs_prune() -> None:
    calls, fake_run = _mk_fake_run()

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        steps = _execute_steps(
            _config(no_import=True, readonly=True, prune=True)
        )

    commands = [str(call["cmd"]) for call in calls]
    assert not any("synapse.phase1_ready" in command for command in commands)
    assert "<SKIP> synapse.phase1_ready --prune" in [
        step.cmd for step in steps
    ]


def test_ambient_readonly_prevails_over_explicit_write(monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_READONLY", "1")

    cfg = _parse_tick_config(["--write"])

    assert cfg.effective_readonly is True


def test_execute_steps_completed_apply_keeps_downstream() -> None:
    calls, fake_run = _mk_fake_run(
        runner_rc=0,
        runner_status="COMPLETED",
    )

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        steps = _execute_steps(_config(no_import=False, readonly=False))

    commands = [str(call["cmd"]) for call in calls]
    assert any("synapse.runner --apply" in command for command in commands)
    assert any("synapse.post_learning" in command for command in commands)
    assert any("synapse.creative_queue" in command for command in commands)
    assert any("synapse.creative_briefs" in command for command in commands)
    assert not any(step.cmd.startswith("<SKIP>") for step in steps)


@pytest.mark.parametrize(
    ("runner_rc", "runner_status"),
    [
        (2, "INSUFFICIENT_EVIDENCE"),
        (3, "LEDGER_UNREADABLE"),
        (0, "SKIPPED"),
        (0, "COMPLETED_DRY_RUN"),
        (0, ""),
        (0, "UNKNOWN_STATUS"),
    ],
)
def test_execute_steps_blocked_or_skipped_learning_stops_downstream(
    runner_rc: int,
    runner_status: str,
) -> None:
    calls, fake_run = _mk_fake_run(
        runner_rc=runner_rc,
        runner_status=runner_status,
    )

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        steps = _execute_steps(_config(no_import=False, readonly=False))

    commands = [str(call["cmd"]) for call in calls]
    assert any("synapse.runner --apply" in command for command in commands)
    assert not any("synapse.post_learning" in command for command in commands)
    assert not any("synapse.creative_queue" in command for command in commands)
    assert not any("synapse.creative_briefs" in command for command in commands)
    assert "<SKIP> synapse.post_learning" in [step.cmd for step in steps]
    assert "<SKIP> synapse.creative_queue" in [step.cmd for step in steps]
    assert "<SKIP> synapse.creative_briefs" in [step.cmd for step in steps]
    expected_tick_status = (
        "OK"
        if runner_rc == 0
        and runner_status in {"SKIPPED", "COMPLETED_DRY_RUN"}
        else "FAIL"
    )
    assert _compute_status(steps, {}) == expected_tick_status


def test_execute_steps_post_learning_failure_stops_creative_downstream() -> None:
    calls, fake_run = _mk_fake_run(
        runner_rc=0,
        runner_status="COMPLETED",
        post_learning_rc=3,
    )

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        steps = _execute_steps(_config(no_import=False, readonly=False))

    commands = [str(call["cmd"]) for call in calls]
    assert any("synapse.post_learning" in command for command in commands)
    assert not any("synapse.creative_queue" in command for command in commands)
    assert not any("synapse.creative_briefs" in command for command in commands)
    assert "<SKIP> synapse.creative_queue" in [step.cmd for step in steps]
    assert "<SKIP> synapse.creative_briefs" in [step.cmd for step in steps]
