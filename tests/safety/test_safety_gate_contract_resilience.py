from types import SimpleNamespace

from synapse.safety.gate import _allowed_from, _reason_from


def test_allowed_from_supports_ok_allowed_success_passed():
    assert _allowed_from(SimpleNamespace(ok=True)) is True
    assert _allowed_from(SimpleNamespace(allowed=True)) is True
    assert _allowed_from(SimpleNamespace(success=True)) is True
    assert _allowed_from(SimpleNamespace(passed=True)) is True
    assert _allowed_from(SimpleNamespace(ok=False)) is False


def test_allowed_from_infers_from_violations_errors_reasons():
    assert _allowed_from(SimpleNamespace(violations=[])) is True
    assert _allowed_from(SimpleNamespace(errors=[])) is True
    assert _allowed_from(SimpleNamespace(reasons=[])) is True

    assert _allowed_from(SimpleNamespace(violations=["x"])) is False
    assert _allowed_from(SimpleNamespace(errors=["x"])) is False
    assert _allowed_from(SimpleNamespace(reasons=["x"])) is False


def test_reason_from_prefers_reason_message_why_detail_then_fallback():
    assert _reason_from(SimpleNamespace(reason="nope"), allowed=False) == "nope"
    assert _reason_from(SimpleNamespace(message="m"), allowed=False) == "m"
    assert _reason_from(SimpleNamespace(why="w"), allowed=False) == "w"
    assert _reason_from(SimpleNamespace(detail="d"), allowed=False) == "d"
    assert _reason_from(SimpleNamespace(violations=["v1"]), allowed=False) == "v1"
    assert _reason_from(SimpleNamespace(), allowed=True) == "OK"
    assert _reason_from(SimpleNamespace(), allowed=False) == "RISK_VIOLATION"