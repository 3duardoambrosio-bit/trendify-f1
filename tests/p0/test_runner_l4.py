from __future__ import annotations

import sys
import types
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from hypothesis import given, settings, strategies as st
import pytest

from synapse.runner import NdjsonLedger, NullLedger, main


# Wrapper: L4 gate indexes ast.Call names; ledger.events is a property (not a call).
def events(ledger: NdjsonLedger | NullLedger) -> List[Dict[str, Any]]:
    return ledger.events


_LOOP_CALLS: list[dict[str, Any]] = []
_STUB_STATUS = "COMPLETED"


class _StubLearningLoopConfig:
    def __init__(
        self,
        min_records: int = 8,
        min_spend_before_learn: float = 15.0,
        require_evidence: bool = True,
        payload_shape_drift_ratio_threshold: float = 0.5,
        payload_shape_drift_min_drops: int = 3,
    ) -> None:
        self.min_records = min_records
        self.min_spend_before_learn = min_spend_before_learn
        self.require_evidence = require_evidence
        self.payload_shape_drift_ratio_threshold = payload_shape_drift_ratio_threshold
        self.payload_shape_drift_min_drops = payload_shape_drift_min_drops


class _StubLearningRunResult:
    def __init__(self, status: str) -> None:
        self.status = status
        self.input_hash = "stub-input-hash"
        self.state_path = "stub-state.json"
        self.weights_path = "stub-weights.json"
        self.report_path = "stub-report.json"

    def __int__(self) -> int:
        raise AssertionError("LearningRunResult must not be coerced with int()")


class _StubLearningLoop:
    def __init__(self, repo: Path | str) -> None:
        self.repo = repo
        _LOOP_CALLS.append({"constructor_arg": repo})

    def run(
        self,
        ledger_obj: Any,
        cfg: _StubLearningLoopConfig,
        force: bool = False,
        dry_run: bool = False,
    ) -> _StubLearningRunResult:
        _LOOP_CALLS[-1]["run"] = {
            "ledger_obj": ledger_obj,
            "cfg": cfg,
            "force": force,
            "dry_run": dry_run,
        }
        return _StubLearningRunResult(_STUB_STATUS)


def _install_stub_learning_loop(status: str = "COMPLETED") -> Any:
    global _STUB_STATUS
    _STUB_STATUS = status
    _LOOP_CALLS.clear()
    old = sys.modules.get("synapse.learning.learning_loop")
    m = types.ModuleType("synapse.learning.learning_loop")
    m.LearningLoop = _StubLearningLoop  # type: ignore[attr-defined]
    m.LearningLoopConfig = _StubLearningLoopConfig  # type: ignore[attr-defined]
    sys.modules["synapse.learning.learning_loop"] = m
    return old


def _restore_stub_learning_loop(old: Any) -> None:
    if old is None:
        sys.modules.pop("synapse.learning.learning_loop", None)
    else:
        sys.modules["synapse.learning.learning_loop"] = old


def test_unit_runner_write_and_aliases_and_main() -> None:
    old = _install_stub_learning_loop()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "events.ndjson"
            led = NdjsonLedger(p)
            payload = {"event_type": "BUY", "ts_utc": "2026-01-01T00:00:00Z"}

            #  L4 necesita ver una llamada explícita a write()
            led.write(payload)

            # Aliases
            led.write_event(payload)
            led.emit(payload)
            led.record(payload)
            led.add_event(payload)

            out = led.iter_events()
            assert isinstance(out, list)
            assert len(events(led)) == 5

        null = NullLedger()
        null.write(payload)
        null.write_event(payload)
        null.emit(payload)
        null.record(payload)
        null.add_event(payload)
        assert len(events(null)) == 5
        assert isinstance(null.iter_events(), list)

        with patch.dict("os.environ", {"SYNAPSE_READONLY": "0"}):
            rc = main(["--root", ".", "--no-ledger", "--apply"])
        assert isinstance(rc, int)
        assert rc == 0
        assert isinstance(_LOOP_CALLS[-1]["constructor_arg"], Path)
        assert isinstance(_LOOP_CALLS[-1]["run"]["cfg"], _StubLearningLoopConfig)
        assert _LOOP_CALLS[-1]["run"]["dry_run"] is False
    finally:
        _restore_stub_learning_loop(old)


def test_runner_default_and_dry_run_do_not_construct_learning_loop(
    capsys,
) -> None:
    old = _install_stub_learning_loop()
    try:
        with patch.dict("os.environ", {"SYNAPSE_READONLY": "0"}):
            assert main([]) == 0
            assert main(["--dry-run"]) == 0

        assert _LOOP_CALLS == []
        output = capsys.readouterr().out
        assert "LEARNING_STATUS=DEFAULT_NOOP" in output
        assert "LEARNING_STATUS=DRY_RUN_NOOP" in output
        assert "LEARNING_WRITES_ALLOWED=false" in output
    finally:
        _restore_stub_learning_loop(old)


def test_runner_readonly_apply_blocks_before_paths_ledger_or_loop(
    tmp_path: Path,
    capsys,
) -> None:
    old = _install_stub_learning_loop()
    missing_root = tmp_path / "must-not-be-created"
    try:
        with patch.dict("os.environ", {"SYNAPSE_READONLY": "1"}):
            rc = main(["--root", str(missing_root), "--apply"])

        assert rc == 2
        assert _LOOP_CALLS == []
        assert not missing_root.exists()
        output = capsys.readouterr().out
        assert "LEARNING_STATUS=READONLY_BLOCKED" in output
        assert "LEARNING_WRITES_ALLOWED=false" in output
        assert "LEARNING_RC=2" in output
    finally:
        _restore_stub_learning_loop(old)


@pytest.mark.parametrize(
    ("status", "expected_rc"),
    [
        ("COMPLETED", 0),
        ("SKIPPED", 0),
        ("INSUFFICIENT_EVIDENCE", 2),
        ("INSUFFICIENT_SPEND", 2),
        ("INSUFFICIENT_RECORDS", 2),
        ("LEDGER_UNREADABLE", 3),
        ("PAYLOAD_SHAPE_DRIFT", 3),
        ("LEARNING_LOOP_LEDGER_FAILED", 3),
        ("UNKNOWN_STATUS", 3),
    ],
)
def test_runner_maps_learning_result_status_without_int_coercion(
    status: str,
    expected_rc: int,
    tmp_path: Path,
    capsys,
) -> None:
    old = _install_stub_learning_loop(status)
    try:
        with patch.dict("os.environ", {"SYNAPSE_READONLY": "0"}):
            rc = main(
                [
                    "--root",
                    str(tmp_path),
                    "--no-ledger",
                    "--apply",
                ]
            )

        assert rc == expected_rc
        call = _LOOP_CALLS[-1]
        assert isinstance(call["constructor_arg"], Path)
        assert call["constructor_arg"] == tmp_path.resolve()
        assert isinstance(call["run"]["cfg"], _StubLearningLoopConfig)
        assert call["run"]["force"] is False
        assert call["run"]["dry_run"] is False
        output = capsys.readouterr().out
        assert f"LEARNING_STATUS={status}" in output
        assert f"LEARNING_RC={expected_rc}" in output
        assert "LEARNING_INPUT_HASH=stub-input-hash" in output
        assert "LEARNING_STATE_PATH=stub-state.json" in output
        assert "LEARNING_REPORT_PATH=stub-report.json" in output
        assert "LEARNING_WEIGHTS_PATH=stub-weights.json" in output
    finally:
        _restore_stub_learning_loop(old)


def test_runner_unexpected_execution_exception_maps_to_rc3(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    old = _install_stub_learning_loop()

    def bomb_run(self, ledger_obj, cfg, force=False, dry_run=False):
        raise RuntimeError("sensitive details must not be printed")

    monkeypatch.setattr(_StubLearningLoop, "run", bomb_run)
    try:
        with patch.dict("os.environ", {"SYNAPSE_READONLY": "0"}):
            rc = main(
                [
                    "--root",
                    str(tmp_path),
                    "--no-ledger",
                    "--apply",
                ]
            )

        assert rc == 3
        output = capsys.readouterr().out
        assert "LEARNING_STATUS=EXECUTION_ERROR" in output
        assert "LEARNING_RC=3" in output
        assert "sensitive details" not in output
    finally:
        _restore_stub_learning_loop(old)


_PAYLOAD = st.fixed_dictionaries(
    {
        "event_type": st.sampled_from(["LEARN", "BUY", "SKIP"]),
        "ts_utc": st.text(min_size=1, max_size=10),
    }
)

@settings(max_examples=40, deadline=None)
@given(_PAYLOAD, st.booleans())
def test_hypothesis_runner_write_and_aliases_and_main(payload: Dict[str, Any], quiet: bool) -> None:
    #  NO fixtures aquí. Todo adentro para evitar HealthCheck.
    old = _install_stub_learning_loop()
    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "events.ndjson"
            led = NdjsonLedger(p)

            #  L4 necesita ver write() también en hypothesis
            led.write(payload)

            led.write_event(payload)
            led.emit(payload)
            led.record(payload)
            led.add_event(payload)

            _ = led.iter_events()
            assert len(events(led)) == 5

        args = ["--root", ".", "--no-ledger", "--apply"]
        if quiet:
            args = ["--root", ".", "--quiet", "--no-ledger", "--apply"]
        with patch.dict("os.environ", {"SYNAPSE_READONLY": "0"}):
            rc = main(args)
        assert isinstance(rc, int)
    finally:
        _restore_stub_learning_loop(old)
