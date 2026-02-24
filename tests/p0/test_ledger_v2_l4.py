# tests/p0/test_ledger_v2_l4.py
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile

import pytest
import deal
from hypothesis import given, settings, strategies as st

from infra.ledger_v2 import (
    LedgerV2,
    LedgerClosedError,
    LedgerIntegrityError,
)


_DEC_2DP_NONZERO = st.decimals(
    min_value=Decimal("-1000000.00"),
    max_value=Decimal("1000000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
).filter(lambda d: d != Decimal("0.00"))

_KIND = st.sampled_from(["CREDIT", "DEBIT", "REFUND", "FEE"])


def _mk(tmp_path: Path) -> LedgerV2:
    # max_buffer grande para que NO auto-flushee en tests
    return LedgerV2(path=tmp_path / "ledger_v2.jsonl", currency="USD", fsync=False, max_buffer=10000)


def _mk_temp() -> tuple[tempfile.TemporaryDirectory[str], LedgerV2]:
    td = tempfile.TemporaryDirectory()
    p = Path(td.name) / "ledger_v2.jsonl"
    return td, LedgerV2(path=p, currency="USD", fsync=False, max_buffer=10000)


def test_write_unit_creates_row_and_id(tmp_path: Path) -> None:
    led = _mk(tmp_path)
    eid = led.write("CREDIT", "10.00", memo="x", meta={"a": "b"})
    assert isinstance(eid, str) and len(eid) >= 8
    rows = led.query(limit=1000)
    assert len(rows) == 1
    assert rows[0].entry_id == eid
    assert rows[0].kind == "CREDIT"
    assert rows[0].amount == "10.00"


@settings(max_examples=120, deadline=None)
@given(_KIND, _DEC_2DP_NONZERO)
def test_write_property_appends_visible_in_query(kind: str, amount: Decimal) -> None:
    td, led = _mk_temp()
    try:
        eid = led.write(kind, amount, memo="m")
        rows = led.query(limit=1000)
        assert len(rows) == 1
        assert rows[0].entry_id == eid
    finally:
        td.cleanup()


def test_flush_unit_writes_file_and_clears_buffer(tmp_path: Path) -> None:
    led = _mk(tmp_path)
    led.write("CREDIT", "1.00")
    led.write("DEBIT", "2.00")
    n = led.flush()
    assert n == 2
    assert (tmp_path / "ledger_v2.jsonl").exists() is True
    assert led.flush() == 0


@settings(max_examples=80, deadline=None)
@given(st.lists(st.tuples(_KIND, _DEC_2DP_NONZERO), min_size=1, max_size=15))
def test_flush_property_returns_count(items: list[tuple[str, Decimal]]) -> None:
    td, led = _mk_temp()
    try:
        for k, a in items:
            led.write(k, a)
        n = led.flush()
        assert n == len(items)
    finally:
        td.cleanup()


def test_query_unit_filters_by_kind(tmp_path: Path) -> None:
    led = _mk(tmp_path)
    led.write("CREDIT", "1.00")
    led.write("DEBIT", "2.00")
    led.write("CREDIT", "3.00")
    credits = led.query(kind="CREDIT", limit=1000)
    assert all(r.kind == "CREDIT" for r in credits)
    assert len(credits) == 2


@settings(max_examples=80, deadline=None)
@given(st.lists(st.tuples(_KIND, _DEC_2DP_NONZERO), min_size=1, max_size=25), _KIND)
def test_query_property_kind_count_matches(items: list[tuple[str, Decimal]], pick: str) -> None:
    td, led = _mk_temp()
    try:
        expected = 0
        for k, a in items:
            led.write(k, a)
            if k == pick:
                expected += 1
        got = led.query(kind=pick, limit=100000)
        assert len(got) == expected
    finally:
        td.cleanup()


def test_verify_integrity_unit_ok_and_corrupt_raises(tmp_path: Path) -> None:
    led = _mk(tmp_path)
    led.write("CREDIT", "1.00")
    led.flush()
    assert led.verify_integrity() is True

    p = tmp_path / "ledger_v2.jsonl"
    p.write_text('{"bad":true}\n', encoding="utf-8")
    with pytest.raises(LedgerIntegrityError):
        led.verify_integrity()


@settings(max_examples=50, deadline=None)
@given(st.lists(st.tuples(_KIND, _DEC_2DP_NONZERO), min_size=1, max_size=20))
def test_verify_integrity_property_roundtrip_ok(items: list[tuple[str, Decimal]]) -> None:
    td, led = _mk_temp()
    try:
        for k, a in items:
            led.write(k, a)
        led.flush()
        assert led.verify_integrity() is True
    finally:
        td.cleanup()


def test_close_unit_prevents_write(tmp_path: Path) -> None:
    led = _mk(tmp_path)
    led.write("CREDIT", "1.00")
    led.close()
    with pytest.raises(LedgerClosedError):
        led.write("CREDIT", "1.00")


@settings(max_examples=60, deadline=None)
@given(_DEC_2DP_NONZERO)
def test_close_property_flushes_and_closes(amount: Decimal) -> None:
    td, led = _mk_temp()
    try:
        led.write("CREDIT", amount)
        led.close()
        assert Path(td.name, "ledger_v2.jsonl").exists() is True
        with pytest.raises(LedgerClosedError):
            led.flush()
    finally:
        td.cleanup()


def test_rejects_float_money_path_unit(tmp_path: Path) -> None:
    led = _mk(tmp_path)
    with pytest.raises(deal.PreContractError):
        led.write("CREDIT", 1.23)  # type: ignore[arg-type]