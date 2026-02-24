from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from infra.result import Err, Ok, Result, err, ok


@given(st.integers())
def test_result_is_ok_not_implemented(_: int) -> None:
    with pytest.raises(NotImplementedError):
        Result().is_ok()


@given(st.integers())
def test_result_is_err_not_implemented(_: int) -> None:
    with pytest.raises(NotImplementedError):
        Result().is_err()


@given(st.integers())
def test_result_map_not_implemented(_: int) -> None:
    with pytest.raises(NotImplementedError):
        Result().map(lambda x: x)


@given(st.integers())
def test_result_map_err_not_implemented(_: int) -> None:
    with pytest.raises(NotImplementedError):
        Result().map_err(lambda e: e)


@given(st.integers())
def test_result_bind_not_implemented(_: int) -> None:
    with pytest.raises(NotImplementedError):
        Result().bind(lambda x: Ok(x))


@given(st.integers(), st.integers())
def test_result_unwrap_or_not_implemented(_: int, default: int) -> None:
    with pytest.raises(NotImplementedError):
        Result().unwrap_or(default)


@given(st.integers())
def test_result_unwrap_or_else_not_implemented(_: int) -> None:
    with pytest.raises(NotImplementedError):
        Result().unwrap_or_else(lambda e: 0)


@given(st.integers())
def test_ok_is_ok(value: int) -> None:
    r = Ok[int, str](value)
    assert r.is_ok() is True


@given(st.integers())
def test_ok_is_err(value: int) -> None:
    r = Ok[int, str](value)
    assert r.is_err() is False


@given(st.integers())
def test_ok_map(value: int) -> None:
    r = Ok[int, str](value)
    out = r.map(lambda x: x + 1)
    assert out.is_ok() is True
    assert isinstance(out, Ok)
    assert out.value == value + 1


@given(st.integers(), st.text())
def test_ok_map_err_keeps_ok(value: int, _: str) -> None:
    r = Ok[int, str](value)
    out = r.map_err(lambda e: len(e))
    assert out.is_ok() is True
    assert isinstance(out, Ok)
    assert out.value == value


@given(st.integers())
def test_ok_bind(value: int) -> None:
    r = Ok[int, str](value)
    out = r.bind(lambda x: Ok[int, str](x * 2))
    assert out.is_ok() is True
    assert isinstance(out, Ok)
    assert out.value == value * 2


@given(st.integers(), st.integers())
def test_ok_unwrap_or(value: int, default: int) -> None:
    r = Ok[int, str](value)
    assert r.unwrap_or(default) == value


@given(st.integers())
def test_ok_unwrap_or_else(value: int) -> None:
    r = Ok[int, str](value)
    assert r.unwrap_or_else(lambda e: -1) == value


@given(st.text())
def test_err_is_ok(error: str) -> None:
    r = Err[int, str](error)
    assert r.is_ok() is False


@given(st.text())
def test_err_is_err(error: str) -> None:
    r = Err[int, str](error)
    assert r.is_err() is True


@given(st.text(), st.integers())
def test_err_map_keeps_err(error: str, _: int) -> None:
    r = Err[int, str](error)
    out = r.map(lambda x: x + 1)
    assert out.is_err() is True
    assert isinstance(out, Err)
    assert out.error == error


@given(st.text())
def test_err_map_err_transforms(error: str) -> None:
    r = Err[int, str](error)
    out = r.map_err(lambda e: len(e))
    assert out.is_err() is True
    assert isinstance(out, Err)
    assert out.error == len(error)


@given(st.text())
def test_err_bind_does_not_call_fn(error: str) -> None:
    r = Err[int, str](error)

    def boom(_: int) -> Result[int, str]:
        raise RuntimeError("must not be called")

    out = r.bind(boom)
    assert out.is_err() is True
    assert isinstance(out, Err)
    assert out.error == error


@given(st.text(), st.integers())
def test_err_unwrap_or_returns_default(error: str, default: int) -> None:
    r = Err[int, str](error)
    assert r.unwrap_or(default) == default


@given(st.text())
def test_err_unwrap_or_else_calls_fn(error: str) -> None:
    r = Err[int, str](error)
    out = r.unwrap_or_else(lambda e: len(e))
    assert out == len(error)


@given(st.integers())
def test_helper_ok(value: int) -> None:
    r = ok(value)
    assert r.is_ok() is True
    assert isinstance(r, Ok)
    assert r.value == value


@given(st.text())
def test_helper_err(error: str) -> None:
    r = err(error)
    assert r.is_err() is True
    assert isinstance(r, Err)
    assert r.error == error