from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import json
import uuid
import os


@dataclass(frozen=True)
class LedgerEvent:
    ts: str
    event_type: str
    entity_type: str
    entity_id: str
    trace_id: str
    payload: Dict[str, Any]


class LedgerNDJSON:
    """
    NDJSON append-only ledger. Single source of truth.

    Design goals:
    - append-only (auditable)
    - utf-8, one JSON per line
    - stable schema
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> LedgerEvent:
        if not event_type:
            raise ValueError("event_type is required")
        if not entity_type:
            raise ValueError("entity_type is required")
        if not entity_id:
            raise ValueError("entity_id is required")

        now = ts or datetime.now(timezone.utc).isoformat()
        tid = trace_id or uuid.uuid4().hex

        ev = LedgerEvent(
            ts=now,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            trace_id=tid,
            payload=payload or {},
        )

        line = json.dumps(asdict(ev), ensure_ascii=False, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        return ev