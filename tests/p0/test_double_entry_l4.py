from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import deal
from hypothesis import given, strategies as st

from infra.double_entry import DoubleEntryLedger, make_entry, new_transaction_id

_ZERO = Decimal("0.00")


def test_empty_ledger_total_is_zero() -> None:
    with TemporaryDirectory() as td:
        led = DoubleEntryLedger(path=str(Path(td) / "de.ndjson"))
        assert led.total_balance() == _ZERO


def test_record_balanced_transaction_ok() -> None:
    with TemporaryDirectory() as td:
        led = DoubleEntryLedger(path=str(Path(td) / "de.ndjson"))
        tx = new_transaction_id()
        entries = [
            make_entry(tx, "meta_ads:spend", Decimal("10.00")),
            make_entry(tx, "cash:bank", Decimal("-10.00")),
        ]
        t = led.record(entries)
        assert t.id == tx
        assert led.total_balance() == _ZERO
        assert led.balance("meta_ads:spend") == Decimal("10.00")
        assert led.balance("cash:bank") == Decimal("-10.00")


def test_record_unbalanced_raises() -> None:
    with TemporaryDirectory() as td:
        led = DoubleEntryLedger(path=str(Path(td) / "de.ndjson"))
        tx = new_transaction_id()
        bad = [
            make_entry(tx, "meta_ads:spend", Decimal("10.00")),
            make_entry(tx, "cash:bank", Decimal("-9.99")),
        ]
        try:
            led.record(bad)
            assert False, "expected deal.PreContractError"
        except deal.PreContractError:
            pass


AMT = st.integers(min_value=0, max_value=5000).map(lambda c: (Decimal(c) / Decimal("100")).quantize(Decimal("0.01")))
N = st.integers(min_value=1, max_value=40)


@given(N, st.lists(AMT, min_size=1, max_size=40))
def test_total_balance_always_zero(n: int, amts: list[Decimal]) -> None:
    with TemporaryDirectory() as td:
        led = DoubleEntryLedger(path=str(Path(td) / "de.ndjson"))
        m = min(n, len(amts))
        for i in range(m):
            a = amts[i]
            tx = new_transaction_id()
            led.record([
                make_entry(tx, "system:learning_budget", a),
                make_entry(tx, "cash:bank", -a),
            ])
        assert led.total_balance() == _ZERO


def test_balance_per_account_correct() -> None:
    with TemporaryDirectory() as td:
        led = DoubleEntryLedger(path=str(Path(td) / "de.ndjson"))
        tx1 = new_transaction_id()
        led.record([
            make_entry(tx1, "cash:bank", Decimal("5.00")),
            make_entry(tx1, "shopify:revenue", Decimal("-5.00")),
        ])
        tx2 = new_transaction_id()
        led.record([
            make_entry(tx2, "cash:bank", Decimal("-2.00")),
            make_entry(tx2, "system:fees", Decimal("2.00")),
        ])
        assert led.total_balance() == _ZERO
        assert led.balance("cash:bank") == Decimal("3.00")

from hypothesis import given, strategies as st

AMT2 = st.integers(min_value=0, max_value=5000).map(lambda c: (Decimal(c) / Decimal("100")).quantize(Decimal("0.01")))

@given(st.lists(AMT2, min_size=1, max_size=40))
def test_balance_hypothesis_matches_sum(amts: list[Decimal]) -> None:
    with TemporaryDirectory() as td:
        led = DoubleEntryLedger(path=str(Path(td) / "de.ndjson"))
        expected = sum(amts, Decimal("0.00")).quantize(Decimal("0.01"))
        for a in amts:
            tx = new_transaction_id()
            led.record([
                make_entry(tx, "meta_ads:spend", a),
                make_entry(tx, "cash:bank", -a),
            ])
        assert led.total_balance() == Decimal("0.00")
        assert led.balance("meta_ads:spend") == expected
        assert led.balance("cash:bank") == -expected
