from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
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


# --- CLI (ops pre-flight) ---------------------------------------------------
#
# synapse.ops_tick shells out to `python -m synapse.ledger_ndjson validate`
# as its ledger pre-flight step. The validation is read-only: it never
# creates, repairs, or truncates the ledger. Exit codes: 0 = clean (a
# missing/empty ledger is clean before the first event), 2 = corrupt lines.

def cmd_validate(path: Path = LEDGER_FILE) -> int:
    if not path.exists():
        print(f"VALIDATE: ledger missing (clean before first event) -> {path}")
        return 0

    good = 0
    bad = 0
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                bad += 1
                print(f"BAD line {index}: invalid JSON: {exc}", file=sys.stderr)
                continue
            if not isinstance(record, dict):
                bad += 1
                print(f"BAD line {index}: not a JSON object", file=sys.stderr)
                continue
            if not str(record.get("kind") or "").strip():
                bad += 1
                print(f"BAD line {index}: missing kind", file=sys.stderr)
                continue
            if not isinstance(record.get("payload"), dict):
                bad += 1
                print(f"BAD line {index}: missing/invalid payload", file=sys.stderr)
                continue
            good += 1

    if bad:
        print(f"VALIDATE: {good} good, {bad} bad -> {path}", file=sys.stderr)
        return 2
    print(f"VALIDATE: {good} good, {bad} bad -> {path}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="synapse.ledger_ndjson",
        description="NDJSON ledger tools (Fase 1; validation is read-only).",
    )
    parser.add_argument(
        "--path",
        default=str(LEDGER_FILE),
        help=f"Ledger path (default: {LEDGER_FILE.as_posix()})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="Validate NDJSON structure (read-only).")

    args = parser.parse_args(argv)
    path = Path(args.path)

    if args.cmd == "validate":
        return cmd_validate(path)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
