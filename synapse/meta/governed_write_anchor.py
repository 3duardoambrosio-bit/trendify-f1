from __future__ import annotations

from typing import Any, Dict, Optional

from infra.ledger_v2 import (
    AMENDMENT_DOCUMENT_TYPE,
    APPEND_ONLY_DOCUMENT_TYPE,
    build_ledger_record,
    wrap_as_amendment,
    wrap_as_append_only,
)
from synapse.infra.time_utc import build_clock_stamp

ANCHOR_CONTRACT_VERSION = "governed-write-anchor.v1"
ANCHOR_SOURCE = "synapse.meta.safe_client"


def build_governed_anchor(
    *,
    event_type: str,
    correlation_id: str,
    idempotency_key: str,
    payload: Dict[str, Any],
    severity: str = "INFO",
    critical: bool = False,
    base_event_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    stamp = build_clock_stamp()

    document_type = AMENDMENT_DOCUMENT_TYPE if base_event_id else APPEND_ONLY_DOCUMENT_TYPE

    record = build_ledger_record(
        event_id=event_id or correlation_id,
        document_type=document_type,
        payload={
            "event_type": event_type,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "payload": payload,
        },
        base_event_id=base_event_id,
        ingest_time=stamp.ingest_time,
        event_time=stamp.event_time,
        metadata={
            "severity": severity,
            "critical": bool(critical),
            "anchor_contract_version": ANCHOR_CONTRACT_VERSION,
            "source": ANCHOR_SOURCE,
        },
    )

    if base_event_id:
        wrapped = wrap_as_amendment(
            record,
            clock_source_id=stamp.clock_source_id,
            clock_unreliable=stamp.clock_unreliable,
            clock_skew_estimate=stamp.clock_skew_estimate,
        )
    else:
        wrapped = wrap_as_append_only(
            record,
            clock_source_id=stamp.clock_source_id,
            clock_unreliable=stamp.clock_unreliable,
            clock_skew_estimate=stamp.clock_skew_estimate,
        )

    return wrapped.to_dict()


def attach_governed_anchor(
    *,
    event_type: str,
    correlation_id: str,
    idempotency_key: str,
    payload: Dict[str, Any],
    severity: str = "INFO",
    critical: bool = False,
    base_event_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    out = dict(payload)
    out["governed_anchor"] = build_governed_anchor(
        event_type=event_type,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        payload=payload,
        severity=severity,
        critical=critical,
        base_event_id=base_event_id,
        event_id=event_id,
    )
    return out
