from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


CANONICALS = [
    "ops/capital_shield_v2.py",
    "infra/ledger_v2.py",
    "ops/spend_gateway_v1.py",
    "ops/safety_middleware.py",
    "synapse/safety/killswitch.py",
    "synapse/safety/circuit.py",
    "infra/atomic_io.py",
    "infra/idempotency_manager.py",
]

PROD_DIRS = ["synapse", "infra", "ops", "buyer", "core", "config"]
ALL_DIRS = ["synapse", "infra", "ops", "buyer", "core", "config", "tools", "tests"]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    count: int
    sample: List[str]


def _run(cmd: List[str]) -> Tuple[int, str, str]:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out, err


def _scan(pattern: str, roots: List[str], sample_cap: int = 25) -> Tuple[int, List[str]]:
    rx = re.compile(pattern)
    count = 0
    sample: List[str] = []

    for r in roots:
        rp = Path(r)
        if not rp.exists():
            continue

        for fp in rp.rglob("*.py"):
            try:
                text = fp.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Count as a hit (encoding issue) and sample it
                count += 1
                if len(sample) < sample_cap:
                    sample.append(f"{fp}:encoding_error")
                continue

            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    count += 1
                    if len(sample) < sample_cap:
                        sample.append(f"{fp}:{i}:{line.strip()}")

    return count, sample


def _git_changed_files() -> List[str]:
    # unstaged + staged
    files: List[str] = []
    for args in (["git", "diff", "--name-only"], ["git", "diff", "--name-only", "--cached"]):
        code, out, err = _run(args)
        if code != 0:
            continue
        files.extend([ln.strip() for ln in out.splitlines() if ln.strip()])
    # de-dup preserving order
    seen = set()
    uniq = []
    for f in files:
        if f in seen:
            continue
        seen.add(f)
        uniq.append(f)
    return uniq


def audit() -> Dict[str, object]:
    checks: List[Check] = []

    changed = _git_changed_files()
    touched = [c for c in changed if c in CANONICALS]
    checks.append(Check("canonicals_touched", ok=(len(touched) == 0), count=len(touched), sample=touched[:25]))

    c_bare, s_bare = _scan(r"^\s*except:\s*$", PROD_DIRS)
    checks.append(Check("bare_except_prod", ok=(c_bare == 0), count=c_bare, sample=s_bare))

    c_print_prod, s_print_prod = _scan(r"\bprint\s*\(", PROD_DIRS)
    checks.append(Check("print_calls_prod", ok=(c_print_prod == 0), count=c_print_prod, sample=s_print_prod))

    c_print_all, s_print_all = _scan(r"\bprint\s*\(", ALL_DIRS)
    checks.append(Check("print_calls_all", ok=True, count=c_print_all, sample=s_print_all))

    c_utc, s_utc = _scan(r"\butcnow\s*\(", PROD_DIRS)
    checks.append(Check("utcnow_prod", ok=(c_utc == 0), count=c_utc, sample=s_utc))

    overall_ok = all(c.ok for c in checks)
    return {
        "overall": "PASS" if overall_ok else "FAIL",
        "checks": [{"name": c.name, "ok": c.ok, "count": c.count, "sample": c.sample} for c in checks],
    }


def main() -> int:
    report = audit()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True))
    sys.stdout.write("\n")
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())