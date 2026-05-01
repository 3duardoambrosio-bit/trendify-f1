from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from synapse.infra.repo_hygiene import scan_repo_hygiene

log = logging.getLogger("repo_hygiene_scan")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="Repo root (default: .)")
    args = ap.parse_args()

    repo = str(Path(args.repo).resolve())
    r = scan_repo_hygiene(repo)

    if r.ok:
        log.info("PASS repo=%s", repo)
        return 0

    log.error("FAIL repo=%s errors=%s findings=%s", repo, r.errors, r.findings)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
