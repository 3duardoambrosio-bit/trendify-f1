from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies as st

from synapse.safety.killswitch import KillSwitch, KillSwitchActivation, KillSwitchLevel


def _safe_text(min_size: int = 1, max_size: int = 24) -> st.SearchStrategy[str]:
    # Avoid surrogate chars (category Cs) that can break some file/console paths.
    return st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=min_size,
        max_size=max_size,
    )


LEVELS = st.sampled_from(list(KillSwitchLevel))
REASON = _safe_text(1, 40)
TRIGGER = _safe_text(1, 40)
TARGET = st.one_of(st.none(), _safe_text(1, 20))


@given(st.integers())
def test_init_in_memory(_: int) -> None:
    ks = KillSwitch()
    assert ks.is_active(KillSwitchLevel.SYSTEM) is False


@given(LEVELS, REASON, TRIGGER, TARGET)
def test_activate_sets_active(level: KillSwitchLevel, reason: str, triggered_by: str, target_id: str | None) -> None:
    ks = KillSwitch()
    act = KillSwitchActivation(level=level, reason=reason, triggered_by=triggered_by, target_id=target_id)
    ks.activate(act)
    assert ks.is_active(level, target_id) is True


@given(LEVELS, TARGET)
def test_is_active_false_when_empty(level: KillSwitchLevel, target_id: str | None) -> None:
    ks = KillSwitch()
    assert ks.is_active(level, target_id) is False


@given(LEVELS, REASON, TRIGGER, TARGET)
def test_clear_removes(level: KillSwitchLevel, reason: str, triggered_by: str, target_id: str | None) -> None:
    ks = KillSwitch()
    ks.activate(KillSwitchActivation(level=level, reason=reason, triggered_by=triggered_by, target_id=target_id))
    assert ks.is_active(level, target_id) is True
    ks.clear(level, target_id)
    assert ks.is_active(level, target_id) is False


@given(LEVELS, REASON, TRIGGER, TARGET)
def test_snapshot_contains_key(level: KillSwitchLevel, reason: str, triggered_by: str, target_id: str | None) -> None:
    ks = KillSwitch()
    ks.activate(KillSwitchActivation(level=level, reason=reason, triggered_by=triggered_by, target_id=target_id))
    snap = ks.snapshot()
    key = f"{level.value}:{target_id or '*'}"
    assert key in snap
    assert snap[key]["level"] == level.value
    assert snap[key]["reason"] == reason


@given(LEVELS, REASON, TRIGGER, TARGET)
def test_persistence_roundtrip(level: KillSwitchLevel, reason: str, triggered_by: str, target_id: str | None) -> None:
    # No pytest tmp_path fixture here: Hypothesis runs multiple examples per test.
    with TemporaryDirectory() as td:
        state_file = Path(td) / "killswitch_state.json"
        ks1 = KillSwitch(state_file=state_file)
        ks1.activate(KillSwitchActivation(level=level, reason=reason, triggered_by=triggered_by, target_id=target_id))

        ks2 = KillSwitch(state_file=state_file)
        assert ks2.is_active(level, target_id) is True


def test_corrupted_state_fail_closed() -> None:
    with TemporaryDirectory() as td:
        state_file = Path(td) / "killswitch_state.json"
        state_file.write_text("{not valid json", encoding="utf-8")
        ks = KillSwitch(state_file=state_file)
        assert ks.is_active(KillSwitchLevel.SYSTEM) is True