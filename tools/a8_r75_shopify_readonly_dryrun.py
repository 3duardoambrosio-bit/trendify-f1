from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synapse.integration.a8_r75_shopify_readonly_dryrun import (
    run_shopify_read_only_dry_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="A8-R75 Shopify read-only dry-run evidence runner."
    )
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    result = run_shopify_read_only_dry_run(Path(args.out_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
