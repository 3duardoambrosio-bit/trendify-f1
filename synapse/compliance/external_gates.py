# V3GAP:G-01_order_status_auto_reply
# V3GAP:oxxo_reminder_day3
# V3GAP:cod_pre_confirmation
"""
External/post-launch gates (declarative stubs).
Require WhatsApp/SMS integration. Activate post-first-sale.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class ExternalGate:
    gate_id: str
    description: str
    channel: str
    phase: str = "post_launch"
    is_implemented: bool = False

ORDER_STATUS_AUTO_REPLY = ExternalGate(
    gate_id="G-01_order_status_auto_reply",
    description="Auto-reply de status de orden via WhatsApp. Requiere WhatsApp Business API.",
    channel="whatsapp",
)
OXXO_REMINDER_DAY3 = ExternalGate(
    gate_id="oxxo_reminder_day3",
    description="Recordatorio dia 3 para vouchers OXXO pendientes de pago.",
    channel="whatsapp_or_sms",
)
COD_PRE_CONFIRMATION = ExternalGate(
    gate_id="cod_pre_confirmation",
    description="Pre-confirmacion de pedido COD antes de despacho.",
    channel="sms_or_whatsapp",
)

EXTERNAL_GATES: List[ExternalGate] = [
    ORDER_STATUS_AUTO_REPLY, OXXO_REMINDER_DAY3, COD_PRE_CONFIRMATION,
]

def get_post_launch_gates() -> List[ExternalGate]:
    return [g for g in EXTERNAL_GATES if g.phase == "post_launch"]

def get_gate_ids() -> List[str]:
    return [g.gate_id for g in EXTERNAL_GATES]