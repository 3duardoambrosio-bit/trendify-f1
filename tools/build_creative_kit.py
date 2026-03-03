from __future__ import annotations

import argparse
import logging
import sys

from synapse.shopify.creative_kit_builder import build_creative_kit
from synapse.shopify.creative_pack_gate import validate_kit_dir

log = logging.getLogger("build_creative_kit")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to source image (jpg/png/webp)")
    ap.add_argument("--out-dir", required=True, help="Output kit directory")
    args = ap.parse_args()

    r = build_creative_kit(args.input, args.out_dir)
    if not r.success:
        log.error("BUILD_FAIL out_dir=%s errors=%s", r.out_dir, r.errors)
        return 1

    g = validate_kit_dir(r.out_dir)
    if not g.allowed:
        log.error("GATE_FAIL out_dir=%s errors=%s buckets=%s", r.out_dir, g.errors, g.buckets)
        return 1

    log.info("OK out_dir=%s files=%s buckets=%s warnings=%s", r.out_dir, len(r.files), g.buckets, r.warnings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
