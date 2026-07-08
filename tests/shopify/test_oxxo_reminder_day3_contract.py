from datetime import datetime, timedelta

from synapse.shopify.oxxo_lifecycle_manager import build_oxxo_reminder_day3_contract


class _FakeValidator:
    def __init__(self, should_remind: bool) -> None:
        self._should_remind = should_remind

    def needs_reminder(self, voucher_created_at: datetime) -> bool:
        return self._should_remind


def test_build_oxxo_reminder_day3_contract_returns_none_when_not_due():
    created_at = datetime.now() - timedelta(hours=1)

    contract = build_oxxo_reminder_day3_contract(
        created_at,
        validator=_FakeValidator(False),
    )

    assert contract is None


def test_build_oxxo_reminder_day3_contract_returns_contract_when_due():
    created_at = datetime.now() - timedelta(hours=49)

    contract = build_oxxo_reminder_day3_contract(
        created_at,
        validator=_FakeValidator(True),
        metadata={"order_id": "ORDER-123"},
    )

    assert contract is not None
    assert contract["gate_id"] == "oxxo_reminder_day3"
    assert contract["channel"] == "whatsapp"
    assert contract["reason"] == "voucher_pending_payment_day3"
    assert contract["voucher_created_at"] == created_at.isoformat()
    assert contract["metadata"] == {"order_id": "ORDER-123"}


def test_build_oxxo_reminder_day3_contract_rejects_invalid_validator():
    created_at = datetime.now()

    try:
        build_oxxo_reminder_day3_contract(created_at, validator=object())
    except TypeError as exc:
        assert "needs_reminder" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for invalid validator")
