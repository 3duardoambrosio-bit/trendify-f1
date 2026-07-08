from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synapse.integration.a8_r76_shopify_fixture_read_path import (
    run_shopify_fixture_read_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate A8-R76 Shopify read-only fixture read path evidence."
    )
    parser.add_argument("--out-dir", required=True, help="Evidence output directory.")
    args = parser.parse_args()

    result = run_shopify_fixture_read_path(Path(args.out_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
