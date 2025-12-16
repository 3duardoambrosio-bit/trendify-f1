from __future__ import annotations

from infra.result import Ok, Err, ok, err, Result


def test_ok_and_err_flags() -> None:
    r1: Result[int, str] = Ok(10)
    r2: Result[int, str] = Err("boom")

    assert r1.is_ok()
    assert not r1.is_err()
    assert not r2.is_ok()
    assert r2.is_err()


def test_ok_map_and_bind() -> None:
    r: Result[int, str] = ok(2)

    r2 = r.map(lambda x: x * 3)
    assert isinstance(r2, Ok)
    assert r2.unwrap_or(0) == 6

    def plus_one(x: int) -> Result[int, str]:
        return Ok(x + 1)

    r3 = r.bind(plus_one)
    assert isinstance(r3, Ok)
    assert r3.unwrap_or(0) == 3


def test_err_propagation() -> None:
    r: Result[int, str] = err("fail")

    r2 = r.map(lambda x: x * 3)
    assert isinstance(r2, Err)
    assert r2.unwrap_or(999) == 999

    def plus_one(x: int) -> Result[int, str]:
        return Ok(x + 1)

    r3 = r.bind(plus_one)
    assert isinstance(r3, Err)
    assert r3.unwrap_or(0) == 0


def test_unwrap_or_else() -> None:
    r_ok: Result[int, str] = ok(5)
    r_err: Result[int, str] = err("x")

    assert r_ok.unwrap_or_else(lambda e: 0) == 5
    assert r_err.unwrap_or_else(lambda e: len(e)) == 1
