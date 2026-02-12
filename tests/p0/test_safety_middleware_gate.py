from decimal import Decimal
from types import SimpleNamespace

from infra.result import Err, Ok
from ops.safety_middleware import check_safety_before_spend
from synapse.safety.killswitch import KillSwitch, KillSwitchActivation, KillSwitchLevel
from synapse.safety.limits import RiskLimits, RiskSnapshot


class DummyCircuitBreaker:
    def __init__(self, can: bool, state_value: str = "open") -> None:
        self._can = can
        self.state = SimpleNamespace(value=state_value)

    def can_execute(self) -> bool:
        return self._can


def _err_text(res: object) -> str:
    # Contract-agnostic: Err may expose .code/.message/.reason/etc.
    for attr in ("reason", "code", "message", "error", "kind"):
        if hasattr(res, attr):
            v = getattr(res, attr)
            if v is None:
                continue
            return str(v)
    return str(res)


def test_safety_middleware_blocks_when_system_killswitch_active(tmp_path):
    ks_file = tmp_path / "killswitch.json"
    ks = KillSwitch(state_file=ks_file)
    ks.activate(KillSwitchActivation(level=KillSwitchLevel.SYSTEM, reason="TEST_ON"))

    res = check_safety_before_spend(Decimal("10.00"), "op1", killswitch=ks)
    assert isinstance(res, Err)
    assert ks.is_active(KillSwitchLevel.SYSTEM) is True


def test_safety_middleware_blocks_when_circuit_open(tmp_path):
    ks_file = tmp_path / "killswitch.json"
    ks = KillSwitch(state_file=ks_file)
    cb = DummyCircuitBreaker(can=False, state_value="open")

    res = check_safety_before_spend(Decimal("10.00"), "op2", killswitch=ks, circuit_breaker=cb)
    assert isinstance(res, Err)
    assert "CIRCUIT_OPEN" in _err_text(res)


def test_safety_middleware_trips_gate_and_activates_system_killswitch(tmp_path):
    ks_file = tmp_path / "killswitch.json"
    ks = KillSwitch(state_file=ks_file)

    limits = RiskLimits(daily_loss_limit="0.05")
    snap = RiskSnapshot(
        monthly_budget="1000.00",
        expected_spend_rate_4h="0.00",
        actual_spend_4h="0.00",
        daily_loss="100.00",
    )

    res = check_safety_before_spend(
        Decimal("10.00"),
        "op3",
        killswitch=ks,
        risk_snapshot=snap,
        risk_limits=limits,
        trip_system_killswitch_on_gate=True,
    )
    assert isinstance(res, Err)
    assert "SAFETY_GATE_TRIPPED" in _err_text(res)
    assert ks.is_active(KillSwitchLevel.SYSTEM) is True


def test_safety_middleware_ok_when_no_gate_inputs(tmp_path):
    ks_file = tmp_path / "killswitch.json"
    ks = KillSwitch(state_file=ks_file)

    res = check_safety_before_spend(Decimal("10.00"), "op4", killswitch=ks)
    assert isinstance(res, Ok)