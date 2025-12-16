from __future__ import annotations

import subprocess
import sys

from core.ledger import Ledger


def main() -> int:
    ledger_path = "data/ledger/events.ndjson"
    cmd = [sys.executable, "scripts/run_launch_dossier_ledger.py", "--path", "data/catalog/candidates_real.csv", "--threshold", "75", "--ledger", ledger_path]
    proc = subprocess.run(cmd)

    ledger = Ledger(path=ledger_path)
    tail = ledger.tail(5)
    print("\n==============================")
    print("LEDGER TAIL (last 5)")
    print("==============================")
    for ev in tail:
        print(f"- {ev.get('ts_utc')} | {ev.get('event_type')} | {ev.get('entity_type')}:{ev.get('entity_id')}")

    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())