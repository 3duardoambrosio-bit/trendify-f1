from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from synapse.ledger_ndjson import append_event, build_event


@dataclass
class LedgerEmitResult:
    ok: bool
    path: str
    used_adapter: str
    error: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    return {"value": payload}


class LedgerWriter:
    """
    Canonical ledger emitter.

    - Source of truth: synapse.ledger_ndjson
    - Preserves previous public interface:
        LedgerWriter(...).emit(event_type, payload, run_id=...)
    - Returns LedgerEmitResult instead of raising on emit failure.
    """

    def __init__(self, fallback_path: str = "runtime/ledger/events.ndjson") -> None:
        self.fallback_path = fallback_path
        self._adapter = "synapse.ledger_ndjson"

    def emit(self, event_type: str, payload: Dict[str, Any], *, run_id: Optional[str] = None) -> LedgerEmitResult:
        eid = str(uuid.uuid4())
        rid = run_id or eid
        path = Path(self.fallback_path)

        body = _normalize_payload(payload)
        body.setdefault("run_id", rid)
        body.setdefault("emitted_at", _utc_now_iso())

        try:
            record = build_event(kind=event_type, payload=body)
            append_event(record, path=path)
            return LedgerEmitResult(
                ok=True,
                path=str(path),
                used_adapter=self._adapter,
            )
        except Exception as e:
            return LedgerEmitResult(
                ok=False,
                path=str(path),
                used_adapter=self._adapter,
                error=str(e),
            )