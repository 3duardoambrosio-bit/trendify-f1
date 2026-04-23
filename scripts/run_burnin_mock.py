from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ops.burnin_mock_harness_v1 import run_burnin_mock


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SYNAPSE burn-in mock harness.")
    parser.add_argument("--cycles", type=int, default=25, help="Number of synthetic cycles to execute.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "burnin_mock",
        help="Directory for ledger, idempotency DB, and summary output.",
    )
    args = parser.parse_args()

    summary = run_burnin_mock(cycles=args.cycles, output_dir=args.out_dir)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
