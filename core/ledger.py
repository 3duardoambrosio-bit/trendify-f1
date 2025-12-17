from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    ts_utc: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ts_utc": self.ts_utc,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "payload": self.payload,
        }


class Ledger:
    """
    NDJSON append-only ledger.
    Default path: data/ledger/events.ndjson (override with env SYNAPSE_LEDGER_PATH).
    """

    def __init__(self, path: Optional[str] = None) -> None:
        p = path or os.getenv("SYNAPSE_LEDGER_PATH") or "data/ledger/events.ndjson"
        self.path = Path(p)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def append(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> LedgerEvent:
        ev = LedgerEvent(
            event_id=str(uuid.uuid4()),
            ts_utc=_utc_now_iso(),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
        line = json.dumps(ev.to_dict(), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        return ev

    def iter_events(self) -> Iterable[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                yield json.loads(raw)

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        events = list(self.iter_events())
        return events[-n:]