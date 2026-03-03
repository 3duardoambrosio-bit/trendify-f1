from __future__ import annotations

import argparse
import logging
import sys

from synapse.shopify.creative_pack_gate import CreativeGateConfig, validate_kit_dir

log = logging.getLogger("creative_pack_gate_cli")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--kit-path", required=True)
    args = ap.parse_args()

    r = validate_kit_dir(args.kit_path, CreativeGateConfig())
    if r.allowed:
        log.info("PASS kit=%s total=%s buckets=%s", args.kit_path, r.total_files, r.buckets)
        return 0
    log.error("FAIL kit=%s errors=%s buckets=%s", args.kit_path, r.errors, r.buckets)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
