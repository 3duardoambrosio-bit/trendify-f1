from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from synapse.infra.time_utc import build_clock_stamp

LEDGER_DIR = Path("runtime/ledger")
LEDGER_FILE = LEDGER_DIR / "events.ndjson"
_TAIL_CHUNK_SIZE = 4096


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _count_nonempty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _read_last_nonempty_line(path: Path) -> Optional[str]:
    if not path.exists():
        return None

    try:
        size = path.stat().st_size
    except OSError:
        return None

    if size <= 0:
        return None

    with path.open("rb") as handle:
        position = size
        buffer = b""

        while position > 0:
            read_size = min(_TAIL_CHUNK_SIZE, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            buffer = chunk + buffer

            for raw in reversed(buffer.splitlines()):
                if raw.strip():
                    return raw.decode("utf-8")

    return None


def next_offset(path: Path = LEDGER_FILE) -> int:
    last_line = _read_last_nonempty_line(path)
    if last_line is None:
        return 0

    try:
        record = json.loads(last_line)
    except json.JSONDecodeError:
        return _count_nonempty_lines(path)

    offset = record.get("offset")
    if isinstance(offset, int) and offset >= 0:
        return offset + 1

    return _count_nonempty_lines(path)


def build_event(
    *,
    kind: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None,
    policy_version: str = "v1",
    payload_schema_version: str = "v1",
    event_time: Optional[str] = None,
    clock_skew_estimate: float = 0.0,
    clock_unreliable: bool = False,
) -> Dict[str, Any]:
    stamp = build_clock_stamp(
        event_time=event_time,
        clock_skew_estimate=clock_skew_estimate,
        clock_unreliable=clock_unreliable,
    )

    return {
        "event_id": event_id or f"{stamp.ingest_time}-{uuid4().hex[:12]}",
        "kind": kind,
        "payload": payload,
        "ingest_time": stamp.ingest_time,
        "event_time": stamp.event_time,
        "clock_source_id": stamp.clock_source_id,
        "clock_skew_estimate": stamp.clock_skew_estimate,
        "clock_unreliable": stamp.clock_unreliable,
        "policy_version": policy_version,
        "payload_schema_version": payload_schema_version,
    }


def append_event(record: Dict[str, Any], *, path: Path = LEDGER_FILE) -> Dict[str, Any]:
    _ensure_parent(path)

    persisted = dict(record)
    persisted["offset"] = next_offset(path)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(persisted) + "\n")

    return persisted


def read_events(path: Path = LEDGER_FILE) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    events: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            events.append(json.loads(raw))
    return events
