from __future__ import annotations

import os, json, hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class LedgerEventV2:
    version: int
    ts: str
    trace_id: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: Dict[str, Any]
    checksum: str

class LedgerV2:
    """
    Ledger NDJSON con:
    - append-only
    - fsync real
    - rotation por tamaño
    - batching
    - checksum integrity
    - query básico
    """
    def __init__(self, base_dir: Path, *, max_bytes: int = 10 * 1024 * 1024, batch_size: int = 10) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int(max_bytes)
        self.batch_size = int(batch_size)
        self._buf: List[LedgerEventV2] = []
        self._current_path: Optional[Path] = None

    def _pick_current_file(self) -> Path:
        if self._current_path and self._current_path.exists():
            if self._current_path.stat().st_size < self.max_bytes:
                return self._current_path

        # rotate / create new
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = self.base_dir / f"ledger_{ts}.ndjson"
        self._current_path = p
        return p

    def _make_event(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> LedgerEventV2:
        core = {
            "version": 2,
            "ts": _utc_now_iso(),
            "trace_id": trace_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
        }
        checksum = _sha256(_canonical_json(core))
        return LedgerEventV2(**core, checksum=checksum)

    def write(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> LedgerEventV2:
        ev = self._make_event(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id),
            payload=payload or {},
            trace_id=str(trace_id),
        )
        self._buf.append(ev)
        if len(self._buf) >= self.batch_size:
            self.flush()
        return ev

    def flush(self) -> None:
        if not self._buf:
            return
        path = self._pick_current_file()
        lines = [ _canonical_json(asdict(ev)) + "\n" for ev in self._buf ]

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())

        self._buf.clear()

    def query(
        self,
        *,
        event_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        since_ts_iso: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        files = sorted(self.base_dir.glob("ledger_*.ndjson"))
        for fp in files:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if since_ts_iso and str(ev.get("ts","")) < since_ts_iso:
                        continue
                    if event_type and ev.get("event_type") != event_type:
                        continue
                    if entity_id and str(ev.get("entity_id","")) != str(entity_id):
                        continue
                    yield ev

    def verify_integrity(self) -> Dict[str, Any]:
        corrupted: List[str] = []
        total = 0
        for ev in self.query():
            total += 1
            checksum = ev.get("checksum")
            core = dict(ev)
            core.pop("checksum", None)
            recalced = _sha256(_canonical_json(core))
            if checksum != recalced:
                corrupted.append(ev.get("trace_id","?"))
        return {"total": total, "corrupted": corrupted, "ok": (len(corrupted) == 0)}

    def close(self) -> None:
        self.flush()
