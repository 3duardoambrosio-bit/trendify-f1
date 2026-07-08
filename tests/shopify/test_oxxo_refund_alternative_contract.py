from datetime import datetime, timedelta, timezone

from synapse.shopify.oxxo_lifecycle_manager import (
    OxxoLifecycleRecord,
    OxxoLifecycleStatus,
    build_oxxo_refund_alternative_contract,
)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 4, day, hour, 0, 0, tzinfo=timezone.utc)


def test_build_oxxo_refund_alternative_contract_returns_none_for_normal_paid_record():
    record = OxxoLifecycleRecord(
        order_id="ord_1",
        voucher_id="vx_1",
        status=OxxoLifecycleStatus.PAGADO,
        issued_at=_dt(1, 10),
        expires_at=_dt(4, 10),
        paid_at=_dt(2, 9),
        orphan_payment=False,
    )

    contract = build_oxxo_refund_alternative_contract(record)

    assert contract is None


def test_build_oxxo_refund_alternative_contract_returns_contract_for_expired_record():
    record = OxxoLifecycleRecord(
        order_id="ord_2",
        voucher_id="vx_2",
        status=OxxoLifecycleStatus.EXPIRADO,
        issued_at=_dt(1, 10),
        expires_at=_dt(4, 10),
        paid_at=None,
        orphan_payment=False,
    )

    contract = build_oxxo_refund_alternative_contract(
        record,
        metadata={"source": "shopify"},
    )

    assert contract is not None
    assert contract["gate_id"] == "A-03_oxxo_refund_alternative"
    assert contract["channel"] == "whatsapp"
    assert contract["reason"] == "route_oxxo_refund_through_alternative_path"
    assert contract["order_id"] == "ord_2"
    assert contract["voucher_id"] == "vx_2"
    assert contract["status"] == "expirado"
    assert contract["orphan_payment"] is False
    assert contract["metadata"] == {"source": "shopify"}


def test_build_oxxo_refund_alternative_contract_returns_contract_for_orphan_payment():
    record = OxxoLifecycleRecord(
        order_id="ord_3",
        voucher_id="vx_3",
        status=OxxoLifecycleStatus.EXPIRADO,
        issued_at=_dt(1, 10),
        expires_at=_dt(4, 10),
        paid_at=_dt(5, 12),
        orphan_payment=True,
    )

    contract = build_oxxo_refund_alternative_contract(record)

    assert contract is not None
    assert contract["status"] == "expirado"
    assert contract["orphan_payment"] is True
    assert contract["paid_at"] == _dt(5, 12).isoformat()


def test_build_oxxo_refund_alternative_contract_requires_record_type():
    try:
        build_oxxo_refund_alternative_contract(object())
    except TypeError as exc:
        assert "OxxoLifecycleRecord" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for invalid record")
