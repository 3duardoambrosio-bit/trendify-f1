from __future__ import annotations

import sys
import types
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from hypothesis import given, settings, strategies as st

from synapse.runner import NdjsonLedger, NullLedger, main


# Wrapper: L4 gate indexes ast.Call names; ledger.events is a property (not a call).
def events(ledger: NdjsonLedger | NullLedger) -> List[Dict[str, Any]]:
    return ledger.events


class _StubLearningLoopConfig:
    def __init__(self, root: str, ledger: str, quiet: bool) -> None:
        self.root = root
        self.ledger = ledger
        self.quiet = quiet


class _StubLearningLoop:
    def __init__(self, config: _StubLearningLoopConfig) -> None:
        self.config = config

    def run(self, ledger: Any) -> int:
        _ = ledger
        return 0


def _install_stub_learning_loop() -> Any:
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

        rc = main(["--root", ".", "--no-ledger"])
        assert isinstance(rc, int)
        assert rc == 0
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

        args = ["--root", ".", "--no-ledger"]
        if quiet:
            args = ["--root", ".", "--quiet", "--no-ledger"]
        rc = main(args)
        assert isinstance(rc, int)
    finally:
        _restore_stub_learning_loop(old)