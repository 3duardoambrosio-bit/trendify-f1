from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from synapse.ledger_ndjson import read_events


def _tail_events(path: str, n: int = 5):
    rows = read_events(Path(path))
    return rows[-n:]


def main() -> int:
    ledger_path = "data/ledger/events.ndjson"
    cmd = [
        sys.executable,
        "scripts/run_launch_dossier_ledger.py",
        "--path",
        "data/catalog/candidates_real.csv",
        "--threshold",
        "75",
        "--ledger",
        ledger_path,
    ]
    proc = subprocess.run(cmd)

    tail = _tail_events(ledger_path, 5)
    print("\n==============================")
    print("LEDGER TAIL (last 5)")
    print("==============================")
    for ev in tail:
        payload = ev.get("payload", {})
        entity_type = payload.get("entity_type", "unknown")
        entity_id = payload.get("entity_id", "unknown")
        event_type = ev.get("kind", "unknown")
        ts = ev.get("event_time") or ev.get("ingest_time") or "unknown"
        print(f"- {ts} | {event_type} | {entity_type}:{entity_id}")

    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())