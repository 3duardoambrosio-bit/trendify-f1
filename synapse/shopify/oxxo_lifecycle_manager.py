# V3GAP:A-01_oxxo_lifecycle_manager

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum

from synapse.shopify.oxxo_validator import OxxoConfig


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class OxxoLifecycleStatus(str, Enum):
    EMITIDO = "EMITIDO"
    PAGADO = "PAGADO"
    EXPIRADO = "EXPIRADO"


@dataclass(frozen=True)
class OxxoLifecycleRecord:
    order_id: str
    voucher_id: str
    status: OxxoLifecycleStatus
    issued_at: datetime
    expires_at: datetime
    paid_at: datetime | None = None
    orphan_payment: bool = False


class OxxoLifecycleManager:
    """
    A-01 minimal lifecycle manager for OXXO vouchers.

    Contract:
    - issue_voucher() => EMITIDO
    - expire_if_due() => EXPIRADO when deadline passed and payment absent
    - register_payment() => PAGADO when payment arrives on time
    - late payment after expiry => remains EXPIRADO + orphan_payment=True
    """

    def __init__(self, config: OxxoConfig | None = None) -> None:
        self._config = config or OxxoConfig()

    @property
    def expiry_hours(self) -> int:
        return int(self._config.expiry_hours)

    def issue_voucher(
        self,
        *,
        order_id: str,
        voucher_id: str,
        issued_at: datetime | None = None,
    ) -> OxxoLifecycleRecord:
        issued = _ensure_utc(issued_at or datetime.now(timezone.utc))
        expires = issued + timedelta(hours=self.expiry_hours)
        return OxxoLifecycleRecord(
            order_id=order_id,
            voucher_id=voucher_id,
            status=OxxoLifecycleStatus.EMITIDO,
            issued_at=issued,
            expires_at=expires,
        )

    def expire_if_due(
        self,
        record: OxxoLifecycleRecord,
        *,
        now: datetime | None = None,
    ) -> OxxoLifecycleRecord:
        current = _ensure_utc(now or datetime.now(timezone.utc))
        if record.status is OxxoLifecycleStatus.PAGADO:
            return record
        if current >= _ensure_utc(record.expires_at):
            return replace(record, status=OxxoLifecycleStatus.EXPIRADO)
        return record

    def register_payment(
        self,
        record: OxxoLifecycleRecord,
        *,
        paid_at: datetime | None = None,
    ) -> OxxoLifecycleRecord:
        paid = _ensure_utc(paid_at or datetime.now(timezone.utc))
        current = self.expire_if_due(record, now=paid)

        if current.status is OxxoLifecycleStatus.EXPIRADO and paid > _ensure_utc(current.expires_at):
            return replace(
                current,
                paid_at=paid,
                orphan_payment=True,
            )

        if current.status is OxxoLifecycleStatus.PAGADO:
            return current

        return replace(
            current,
            status=OxxoLifecycleStatus.PAGADO,
            paid_at=paid,
            orphan_payment=False,
        )

    def orphan_payment_count(self, records: list[OxxoLifecycleRecord]) -> int:
        return sum(1 for item in records if item.orphan_payment)

    def can_auto_fulfill(self, record: OxxoLifecycleRecord) -> bool:
        return record.status is OxxoLifecycleStatus.PAGADO and not record.orphan_payment

# V3GAP:oxxo_reminder_day3
def build_oxxo_reminder_day3_contract(
    voucher_created_at,
    *,
    validator=None,
    channel: str = "whatsapp",
    metadata=None,
):
    """
    Build the day-3 OXXO reminder contract only when the existing validator
    says the voucher already crossed the configured reminder threshold.
    """
    import inspect
    from datetime import datetime
    from synapse.shopify import oxxo_validator as _oxxo_validator_module

    if not isinstance(voucher_created_at, datetime):
        raise TypeError("voucher_created_at must be datetime")

    resolved_validator = validator
    if resolved_validator is None:
        validator_classes = [
            obj
            for obj in vars(_oxxo_validator_module).values()
            if inspect.isclass(obj) and hasattr(obj, "needs_reminder")
        ]
        if not validator_classes:
            raise RuntimeError(
                "No validator class with needs_reminder found in synapse.shopify.oxxo_validator"
            )
        resolved_validator = validator_classes[0]()

    if not hasattr(resolved_validator, "needs_reminder"):
        raise TypeError("validator must expose needs_reminder")

    if not resolved_validator.needs_reminder(voucher_created_at):
        return None

    contract = {
        "gate_id": "oxxo_reminder_day3",
        "channel": channel,
        "reason": "voucher_pending_payment_day3",
        "voucher_created_at": voucher_created_at.isoformat(),
    }

    if metadata is not None:
        contract["metadata"] = dict(metadata)

    return contract

# V3GAP:A-03_oxxo_refund_alternative
def build_oxxo_refund_alternative_contract(
    record,
    *,
    channel: str = "whatsapp",
    metadata=None,
):
    """
    Build the lightweight operational contract for OXXO refunds that must
    follow an alternative path instead of the normal auto-fulfillment flow.
    """
    if not isinstance(record, OxxoLifecycleRecord):
        raise TypeError("record must be OxxoLifecycleRecord")

    requires_alternative = (
        record.status is OxxoLifecycleStatus.EXPIRADO
        or bool(record.orphan_payment)
    )

    if not requires_alternative:
        return None

    contract = {
        "gate_id": "A-03_oxxo_refund_alternative",
        "channel": channel,
        "reason": "route_oxxo_refund_through_alternative_path",
        "order_id": record.order_id,
        "voucher_id": record.voucher_id,
        "status": record.status.name.lower(),
        "orphan_payment": bool(record.orphan_payment),
    }

    if record.paid_at is not None:
        contract["paid_at"] = record.paid_at.isoformat()

    if metadata is not None:
        contract["metadata"] = dict(metadata)

    return contract
