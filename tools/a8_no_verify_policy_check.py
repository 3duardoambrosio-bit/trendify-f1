from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BYPASS_FLAG = "-" * 2 + "no" + "-" + "verify"


def main() -> int:
    result = subprocess.run(
        ["git", "grep", "-n", "-I", "--", BYPASS_FLAG, "--", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    if result.returncode == 1:
        print("NO_VERIFY_TEXT_COUNT=0")
        return 0

    if result.returncode == 0:
        offenders = [line for line in result.stdout.splitlines() if line.strip()]
        print(f"NO_VERIFY_TEXT_COUNT={len(offenders)}")
        print("NO_VERIFY_REFS_BEGIN")
        for offender in offenders:
            print(offender)
        print("NO_VERIFY_REFS_END")
        return 1

    print("GIT_GREP_POLICY_CHECK_ERROR=1", file=sys.stderr)
    print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
