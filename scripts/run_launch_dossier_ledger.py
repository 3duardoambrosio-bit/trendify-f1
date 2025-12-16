from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Dict, Any

from core.ledger import Ledger


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--threshold", type=float, default=75.0)
    ap.add_argument("--ledger", default="data/ledger/events.ndjson")
    args, extra = ap.parse_known_args()

    cmd = [sys.executable, "scripts/run_launch_dossier.py", "--path", args.path, "--threshold", str(args.threshold)] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True)

    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    print(proc.stdout, end="")

    ledger = Ledger(path=args.ledger)
    payload: Dict[str, Any] = {
        "cmd": cmd,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    ledger.append("LAUNCH_DOSSIER_RUN", "system", "launch_dossier", payload)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())