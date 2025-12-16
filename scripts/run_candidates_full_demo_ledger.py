from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Any, Dict

from core.ledger import Ledger


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="data/catalog/candidates_full.csv")
    ap.add_argument("--ledger", default="data/ledger/events.ndjson")
    args, extra = ap.parse_known_args()

    cmd = [sys.executable, "scripts/run_candidates_full_demo.py", "--path", args.path] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True)

    print(proc.stdout, end="")

    Ledger(path=args.ledger).append(
        "CANDIDATES_FULL_RUN",
        "system",
        "candidates_full",
        {"cmd": cmd, "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr},
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())