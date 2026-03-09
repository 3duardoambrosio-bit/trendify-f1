from __future__ import annotations

from unittest.mock import patch

from synapse.ops_tick import StepResult, TickConfig, _execute_steps


def _mk_fake_run():
    calls = []

    def _fake_run(cmd, env_overrides=None):
        calls.append(" ".join(cmd))
        return StepResult(cmd=" ".join(cmd), returncode=0, stdout_tail="", stderr_tail="")

    return calls, _fake_run


def test_execute_steps_no_import_readonly_skips_downstream_creative_steps():
    calls, fake_run = _mk_fake_run()
    cfg = TickConfig(
        csv="auto",
        platform="meta",
        product_id="34357",
        prune=False,
        no_import=True,
        effective_readonly=True,
    )

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        steps = _execute_steps(cfg)

    cmds = [s.cmd for s in steps]
    assert "<SKIP> synapse.runner" in cmds
    assert "<SKIP> synapse.creative_queue" in cmds
    assert "<SKIP> synapse.creative_briefs" in cmds

    assert any("synapse.ledger_ndjson validate" in c for c in calls)
    assert any("synapse.post_learning" in c for c in calls)
    assert not any("synapse.creative_queue" in c for c in calls)
    assert not any("synapse.creative_briefs" in c for c in calls)


def test_execute_steps_normal_mode_keeps_downstream_creative_steps():
    calls, fake_run = _mk_fake_run()
    cfg = TickConfig(
        csv="auto",
        platform="meta",
        product_id="34357",
        prune=False,
        no_import=False,
        effective_readonly=False,
    )

    with patch("synapse.ops_tick._run", side_effect=fake_run):
        steps = _execute_steps(cfg)

    cmds = [s.cmd for s in steps]
    assert not any(cmd == "<SKIP> synapse.creative_queue" for cmd in cmds)
    assert not any(cmd == "<SKIP> synapse.creative_briefs" for cmd in cmds)

    assert any("synapse.creative_queue" in c for c in calls)
    assert any("synapse.creative_briefs" in c for c in calls)