# V3GAP:A-01_oxxo_lifecycle_manager

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from synapse.shopify.oxxo_lifecycle_manager import (
    OxxoLifecycleManager,
    OxxoLifecycleStatus,
)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 4, day, hour, 0, 0, tzinfo=timezone.utc)


def test_issue_voucher_emits_with_default_expiry():
    mgr = OxxoLifecycleManager()
    issued_at = _dt(1, 10)

    record = mgr.issue_voucher(order_id="ord_1", voucher_id="vx_1", issued_at=issued_at)

    assert record.status is OxxoLifecycleStatus.EMITIDO
    assert record.issued_at == issued_at
    assert record.expires_at == issued_at + timedelta(hours=72)
    assert record.orphan_payment is False


def test_register_payment_before_expiry_marks_pagado():
    mgr = OxxoLifecycleManager()
    record = mgr.issue_voucher(order_id="ord_2", voucher_id="vx_2", issued_at=_dt(1, 9))

    paid = mgr.register_payment(record, paid_at=_dt(2, 9))

    assert paid.status is OxxoLifecycleStatus.PAGADO
    assert paid.orphan_payment is False
    assert mgr.can_auto_fulfill(paid) is True


def test_expire_if_due_marks_expirado():
    mgr = OxxoLifecycleManager()
    record = mgr.issue_voucher(order_id="ord_3", voucher_id="vx_3", issued_at=_dt(1, 8))

    expired = mgr.expire_if_due(record, now=_dt(5, 9))

    assert expired.status is OxxoLifecycleStatus.EXPIRADO
    assert expired.orphan_payment is False


def test_register_payment_after_expiry_marks_orphan_and_stays_expired():
    mgr = OxxoLifecycleManager()
    record = mgr.issue_voucher(order_id="ord_4", voucher_id="vx_4", issued_at=_dt(1, 8))

    late_paid = mgr.register_payment(record, paid_at=_dt(5, 9))

    assert late_paid.status is OxxoLifecycleStatus.EXPIRADO
    assert late_paid.orphan_payment is True
    assert mgr.can_auto_fulfill(late_paid) is False


def test_payment_exactly_at_expiry_is_accepted():
    mgr = OxxoLifecycleManager()
    record = mgr.issue_voucher(order_id="ord_5", voucher_id="vx_5", issued_at=_dt(1, 8))

    exact = mgr.register_payment(record, paid_at=record.expires_at)

    assert exact.status is OxxoLifecycleStatus.PAGADO
    assert exact.orphan_payment is False


def test_orphan_payment_count_counts_only_late_payments():
    mgr = OxxoLifecycleManager()

    on_time = mgr.register_payment(
        mgr.issue_voucher(order_id="ord_6", voucher_id="vx_6", issued_at=_dt(1, 8)),
        paid_at=_dt(2, 8),
    )
    orphan = mgr.register_payment(
        mgr.issue_voucher(order_id="ord_7", voucher_id="vx_7", issued_at=_dt(1, 8)),
        paid_at=_dt(6, 8),
    )

    assert mgr.orphan_payment_count([on_time, orphan]) == 1