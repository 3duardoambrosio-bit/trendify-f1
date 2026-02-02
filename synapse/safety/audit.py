from __future__ import annotations
from infra.time_utils import now_utc

from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime
import hashlib
import json
import os


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    timestamp: str
    actor: str
    correlation_id: str
    data: Dict[str, Any]
    prev_hash: Optional[str]
    hash: str


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class AuditTrail:
    """
    Append-only NDJSON with hash chain.
    v1 uses local filesystem; later we can swap backend.
    """
    def __init__(self, path: str = "data/audit/events.ndjson") -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def append(
        self,
        event_type: str,
        data: Dict[str, Any],
        actor: str = "system",
        correlation_id: str = "corr-unknown",
    ) -> AuditEvent:
        prev = self._last_hash()
        payload = {
            "event_type": event_type,
            "timestamp": now_utc().isoformat(),
            "actor": actor,
            "correlation_id": correlation_id,
            "data": data,
            "prev_hash": prev,
        }
        h = _sha256(_canonical(payload))
        evt = AuditEvent(
            event_type=payload["event_type"],
            timestamp=payload["timestamp"],
            actor=payload["actor"],
            correlation_id=payload["correlation_id"],
            data=payload["data"],
            prev_hash=payload["prev_hash"],
            hash=h,
        )
        line = _canonical({
            "event_type": evt.event_type,
            "timestamp": evt.timestamp,
            "actor": evt.actor,
            "correlation_id": evt.correlation_id,
            "data": evt.data,
            "prev_hash": evt.prev_hash,
            "hash": evt.hash,
        })
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return evt

    def verify(self) -> bool:
        prev: Optional[str] = None
        if not os.path.exists(self.path):
            return True
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                # verify chain link
                if obj.get("prev_hash") != prev:
                    return False
                # verify hash
                payload = {
                    "event_type": obj["event_type"],
                    "timestamp": obj["timestamp"],
                    "actor": obj["actor"],
                    "correlation_id": obj["correlation_id"],
                    "data": obj["data"],
                    "prev_hash": obj["prev_hash"],
                }
                if _sha256(_canonical(payload)) != obj.get("hash"):
                    return False
                prev = obj.get("hash")
        return True

    def _last_hash(self) -> Optional[str]:
        if not os.path.exists(self.path):
            return None
        last = None
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    last = raw
        if not last:
            return None
        try:
            return json.loads(last).get("hash")
        except Exception:
            return None
