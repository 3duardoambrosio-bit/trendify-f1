from synapse.safety.killswitch import KillSwitch, KillSwitchLevel


def test_killswitch_corrupt_state_file_fail_closed(tmp_path):
    p = tmp_path / "killswitch.json"
    p.write_text("{not valid json", encoding="utf-8")

    ks = KillSwitch(state_file=p)
    assert ks.is_active(KillSwitchLevel.SYSTEM) is True