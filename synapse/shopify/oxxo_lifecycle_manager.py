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