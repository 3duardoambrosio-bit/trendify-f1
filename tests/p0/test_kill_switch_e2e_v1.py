from __future__ import annotations

from decimal import Decimal
from time import perf_counter

from ops.safety_middleware import check_safety_before_spend
from synapse.safety.killswitch import (
    KillSwitch,
    KillSwitchActivation,
    KillSwitchLevel,
)


def _result_text(result: object) -> str:
    parts: list[str] = []

    for attr in ("error", "reason", "message", "value"):
        if hasattr(result, attr):
            try:
                parts.append(str(getattr(result, attr)))
            except Exception:
                pass

    if hasattr(result, "__dict__"):
        try:
            parts.append(str(getattr(result, "__dict__")))
        except Exception:
            pass

    parts.append(str(result))
    return " ".join(parts)


def _result_allows_spend(result: object) -> bool:
    for attr in ("is_ok", "ok", "success", "allowed"):
        if hasattr(result, attr):
            value = getattr(result, attr)
            if callable(value):
                try:
                    return bool(value())
                except TypeError:
                    pass
            else:
                return bool(value)

    text = _result_text(result).lower()
    if "killswitch_active" in text or "kill switch is on" in text:
        return False
    if "err" in text or "fail" in text or "blocked" in text:
        return False
    return bool(result)


def test_system_kill_switch_blocks_pre_spend_in_under_one_second_and_persists(tmp_path) -> None:
    state_file = tmp_path / "killswitch_state.json"
    kill_switch = KillSwitch(state_file=state_file)

    kill_switch.activate(
        KillSwitchActivation(
            level=KillSwitchLevel.SYSTEM,
            reason="a8_r19_e2e_contract",
            triggered_by="test_kill_switch_e2e_v1",
        )
    )

    assert kill_switch.is_active(KillSwitchLevel.SYSTEM)
    assert state_file.exists()

    started = perf_counter()
    first = check_safety_before_spend(
        Decimal("1.00"),
        "a8-r19-kill-switch-first",
        killswitch=kill_switch,
    )
    elapsed = perf_counter() - started

    assert elapsed < 1.0
    assert not _result_allows_spend(first)

    first_text = _result_text(first)
    assert "KILLSWITCH_ACTIVE" in first_text or "kill switch is on" in first_text

    second = check_safety_before_spend(
        Decimal("1.00"),
        "a8-r19-kill-switch-second",
        killswitch=kill_switch,
    )

    assert not _result_allows_spend(second)

    reloaded = KillSwitch(state_file=state_file)
    assert reloaded.is_active(KillSwitchLevel.SYSTEM)

    snapshot_text = str(reloaded.snapshot())
    assert "a8_r19_e2e_contract" in snapshot_text
    assert "test_kill_switch_e2e_v1" in snapshot_text


def test_inactive_system_kill_switch_allows_pre_spend_in_under_one_second(tmp_path) -> None:
    state_file = tmp_path / "inactive_killswitch_state.json"
    kill_switch = KillSwitch(state_file=state_file)

    assert not kill_switch.is_active(KillSwitchLevel.SYSTEM)

    started = perf_counter()
    result = check_safety_before_spend(
        Decimal("1.00"),
        "a8-r21-kill-switch-inactive-allows",
        killswitch=kill_switch,
    )
    elapsed = perf_counter() - started

    assert elapsed < 1.0
    assert _result_allows_spend(result)

    result_text = _result_text(result)
    assert "KILLSWITCH_ACTIVE" not in result_text
    assert "kill switch is on" not in result_text.lower()

    reloaded = KillSwitch(state_file=state_file)
    assert not reloaded.is_active(KillSwitchLevel.SYSTEM)
