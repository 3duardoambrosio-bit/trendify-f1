from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

PROD_DIRS = [Path("synapse"), Path("infra"), Path("ops"), Path("buyer"), Path("core"), Path("config")]

CANONICALS = {
    Path("ops/capital_shield_v2.py"),
    Path("infra/ledger_v2.py"),
    Path("ops/spend_gateway_v1.py"),
    Path("ops/safety_middleware.py"),
    Path("synapse/safety/killswitch.py"),
    Path("synapse/safety/circuit.py"),
    Path("infra/atomic_io.py"),
    Path("infra/idempotency_manager.py"),
}

RX_BARE_EXCEPT = re.compile(r"(?m)^(?P<indent>[ \t]*)except[ \t]*:[ \t]*$")
RX_PRINT_CALL = re.compile(r"\bprint\s*\(")
RX_UTCNOW = re.compile(r"\butcnow\s*\(")

def _is_tests(p: Path) -> bool:
    s = p.as_posix().lower()
    return "/tests/" in s or s.endswith("/test.py") or s.endswith("_test.py")

def _is_excluded(p: Path) -> bool:
    # Exclude canonicals from pattern scans (rule: no tocar canonicals)
    if p in CANONICALS:
        return True
    # Exclude tools entirely from "prod" scans
    if p.as_posix().lower().startswith("tools/"):
        return True
    # Exclude tests
    if _is_tests(p):
        return True
    return False

def _git_diff_paths() -> List[str]:
    p = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True)
    p2 = subprocess.run(["git", "diff", "--name-only", "--cached"], capture_output=True, text=True)
    out = []
    out.extend([x.strip() for x in p.stdout.splitlines() if x.strip()])
    out.extend([x.strip() for x in p2.stdout.splitlines() if x.strip()])
    return sorted(set(out))

def _scan_files(rx: re.Pattern) -> List[str]:
    hits: List[str] = []
    for root in PROD_DIRS:
        if not root.exists():
            continue
        for fp in root.rglob("*.py"):
            rel = Path(fp.as_posix())
            if _is_excluded(rel):
                continue
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    rel_s = rel.as_posix().replace("/", "\\")
                    hits.append(f"{rel_s}:{i}:{line.strip()}")
    return hits

def main() -> int:
    checks: List[Dict[str, Any]] = []

    changed = set(_git_diff_paths())
    canon_touched = sorted([p.as_posix().replace('/','\\\\') for p in CANONICALS if p.as_posix() in changed])
    checks.append({"name":"canonicals_touched","count":len(canon_touched),"ok":len(canon_touched)==0,"sample":canon_touched})

    bare_hits = _scan_files(RX_BARE_EXCEPT)
    checks.append({"name":"bare_except_prod","count":len(bare_hits),"ok":len(bare_hits)==0,"sample":bare_hits[:50]})

    print_hits = _scan_files(RX_PRINT_CALL)
    checks.append({"name":"print_calls_prod","count":len(print_hits),"ok":len(print_hits)==0,"sample":print_hits[:50]})

    all_print = []
    # keep "print_calls_all" informational only (ok=true always)
    all_print.extend(print_hits)
    checks.append({"name":"print_calls_all","count":len(all_print),"ok":True,"sample":all_print[:50]})

    utc_hits = _scan_files(RX_UTCNOW)
    checks.append({"name":"utcnow_prod","count":len(utc_hits),"ok":len(utc_hits)==0,"sample":utc_hits[:50]})

    overall = "PASS" if all(c["ok"] for c in checks if c["name"] != "print_calls_all") else "FAIL"
    out = {"checks": checks, "overall": overall}
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=False))
    return 0 if overall == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
