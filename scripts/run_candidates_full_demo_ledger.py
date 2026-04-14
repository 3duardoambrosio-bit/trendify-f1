from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from synapse.ledger_ndjson import append_event, build_event


def _append_run_event(ledger_path: str, *, event_type: str, payload: Dict[str, Any]) -> None:
    path = Path(ledger_path)
    body = {
        "entity_type": "system",
        "entity_id": "candidates_full",
        **payload,
    }
    record = build_event(kind=event_type, payload=body)
    append_event(record, path=path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="data/catalog/candidates_full.csv")
    ap.add_argument("--ledger", default="data/ledger/events.ndjson")
    args, extra = ap.parse_known_args()

    cmd = [sys.executable, "scripts/run_candidates_full_demo.py", "--path", args.path] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True)

    print(proc.stdout, end="")

    _append_run_event(
        args.ledger,
        event_type="CANDIDATES_FULL_RUN",
        payload={
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        },
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())