from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

@dataclass
class LedgerEmitResult:
    ok: bool
    path: str
    used_adapter: str
    error: Optional[str] = None

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _ensure_dir(p: str) -> None:
    os.makedirs(os.path.dirname(p), exist_ok=True)

def _write_ndjson_fsync(path: str, obj: Dict[str, Any]) -> None:
    _ensure_dir(path)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    # Use append + fsync for durability
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

class LedgerWriter:
    """Best-effort adapter to your existing ledger; safe fallback NDJSON with fsync."""

    def __init__(self, fallback_path: str = "data/ledger/events.ndjson") -> None:
        self.fallback_path = fallback_path
        self._adapter = self._detect_adapter()

    def _detect_adapter(self) -> str:
        # Try common adapter names without breaking if they don't exist.
        try:
            import core.ledger as cl  # type: ignore
            # Heuristics
            if hasattr(cl, "append_event") and callable(getattr(cl, "append_event")):
                return "core.ledger.append_event"
            if hasattr(cl, "Ledger"):
                return "core.ledger.Ledger"
        except Exception:
            pass
        return "fallback_ndjson"

    def emit(self, event_type: str, payload: Dict[str, Any], *, run_id: Optional[str] = None) -> LedgerEmitResult:
        eid = str(uuid.uuid4())
        rid = run_id or eid
        event = {
            "event_id": eid,
            "run_id": rid,
            "ts_utc": _utc_now_iso(),
            "type": event_type,
            "payload": payload,
        }

        try:
            if self._adapter == "core.ledger.append_event":
                import core.ledger as cl  # type: ignore
                cl.append_event(event_type, payload, run_id=rid)  # type: ignore
                return LedgerEmitResult(ok=True, path="(core ledger)", used_adapter=self._adapter)
            if self._adapter == "core.ledger.Ledger":
                import core.ledger as cl  # type: ignore
                ledger = cl.Ledger()  # type: ignore
                ledger.append(event)  # type: ignore
                return LedgerEmitResult(ok=True, path="(core ledger)", used_adapter=self._adapter)

            _write_ndjson_fsync(self.fallback_path, event)
            return LedgerEmitResult(ok=True, path=self.fallback_path, used_adapter=self._adapter)
        except Exception as e:
            return LedgerEmitResult(ok=False, path=self.fallback_path, used_adapter=self._adapter, error=str(e))
