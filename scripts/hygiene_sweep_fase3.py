from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


UTC_FILES = {
    "infra/blindaje.py",
    "infra/bitacora_auto.py",
    "ops/enrich_candidates_f1_v2.py",
    "ops/systems/tribunal.py",
    "ops/dropi_product_finder.py",
    "synapse/safety/audit.py",
    "scripts/dropi_enrich_dump_with_catalog.py",
    "scripts/dropi_catalog_ingest.py",
    "synapse/pulse/market_pulse.py",
    "ops/spend_gateway_v1.py",
    "ops/enrich_candidates_f1.py",
    "ops/systems/hypothesis_tracker.py",
    "synapse/learning/learning_loop.py",
    "ops/tests/test_tribunal.py",
}

BARE_EXCEPT_FILES = {
    "synapse/infra/ledger.py",
    "synapse/marketing_os/wave_runner.py",
    "scripts/normalize_dropi_pack_to_candidates_csv.py",
    "ops/enrich_candidates_f1_v2.py",
    "synapse/discovery/catalog_scanner.py",
    "scripts/run_product_finder_dropi_dump.py",
    "synapse/discovery/niche_selector.py",
}

ROOT_MARKERS = ["pyproject.toml", ".git"]


def find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for _ in range(8):
        if any((p / m).exists() for m in ROOT_MARKERS):
            return p
        p = p.parent
    return start.resolve()


def insert_now_utc_import(src: str) -> str:
    imp = "from infra.time_utils import now_utc\n"
    if imp in src:
        return src

    lines = src.splitlines(keepends=True)

    i = 0
    # shebang
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    # encoding cookie
    if i < len(lines) and re.match(r"^#.*coding[:=]\s*[-\w.]+", lines[i]):
        i += 1
    # leading comments / blank lines
    while i < len(lines) and (lines[i].strip() == "" or lines[i].lstrip().startswith("#")):
        i += 1
    # __future__ imports must remain at top
    while i < len(lines) and lines[i].startswith("from __future__ import"):
        i += 1

    # Insert import + one blank line after it if not already separated
    out = lines[:i] + [imp, "\n"] + lines[i:]
    return "".join(out)


def patch_bare_except(src: str) -> tuple[str, int]:
    # Replace lines that are exactly "except:" (allow indentation)
    pat = re.compile(r"^([ \t]*)except\s*:\s*$", re.MULTILINE)
    new, n = pat.subn(r"\1except Exception:", src)
    return new, n


def patch_utcnow(src: str) -> tuple[str, int]:
    n_total = 0

    # Replace common datetime utcnow call forms with now_utc()
    patterns = [
        r"\bdatetime\.utcnow\(\)",
        r"\bdatetime\.datetime\.utcnow\(\)",
        r"\b_dt\.datetime\.utcnow\(\)",
        r"\b_dt\.utcnow\(\)",
        r"\bdt\.datetime\.utcnow\(\)",
        r"\bdt\.utcnow\(\)",
        r"\b_dt\.datetime\.datetime\.utcnow\(\)",  # paranoia
    ]
    for p in patterns:
        src, n = re.subn(p, "now_utc()", src)
        n_total += n

    # Fix isoformat() + "Z" cases to avoid "+00:00Z"
    src = src.replace('now_utc().isoformat() + "Z"', 'now_utc().isoformat().replace("+00:00","Z")')
    src = src.replace("now_utc().isoformat() + 'Z'", 'now_utc().isoformat().replace("+00:00","Z")')
    src = src.replace('now_utc().replace(microsecond=0).isoformat() + "Z"', 'now_utc().replace(microsecond=0).isoformat().replace("+00:00","Z")')
    src = src.replace("now_utc().replace(microsecond=0).isoformat() + 'Z'", 'now_utc().replace(microsecond=0).isoformat().replace("+00:00","Z")')

    # If we introduced now_utc(), ensure import exists
    if "now_utc(" in src:
        src = insert_now_utc_import(src)

    return src, n_total


def file_has_bare_except(path: Path) -> bool:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return re.search(r"^([ \t]*)except\s*:\s*$", txt, re.MULTILINE) is not None


def file_has_utcnow(path: Path) -> bool:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return re.search(r"utcnow\(", txt) is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="apply changes")
    ap.add_argument("--check", action="store_true", help="check only; exit 1 if issues remain")
    args = ap.parse_args()

    root = find_repo_root(Path.cwd())
    targets = sorted({*UTC_FILES, *BARE_EXCEPT_FILES})

    changed = []
    stats = {"bare_except_fixed": 0, "utcnow_fixed": 0}

    for rel in targets:
        p = (root / rel).resolve()
        if not p.exists():
            continue

        src = p.read_text(encoding="utf-8", errors="strict")

        new_src = src
        n1 = n2 = 0

        if rel in BARE_EXCEPT_FILES:
            new_src, n1 = patch_bare_except(new_src)

        if rel in UTC_FILES:
            new_src, n2 = patch_utcnow(new_src)

        if args.apply and new_src != src:
            p.write_text(new_src, encoding="utf-8", newline="\n")
            changed.append(rel)

        stats["bare_except_fixed"] += n1
        stats["utcnow_fixed"] += n2

    # Check status after apply (or current state if check-only)
    remaining_bare = []
    remaining_utc = []
    for rel in targets:
        p = (root / rel).resolve()
        if not p.exists():
            continue
        if rel in BARE_EXCEPT_FILES and file_has_bare_except(p):
            remaining_bare.append(rel)
        if rel in UTC_FILES and file_has_utcnow(p):
            remaining_utc.append(rel)

    print("== FASE3 HYGIENE SWEEP ==")
    print(f"repo_root: {root}")
    if args.apply:
        print(f"changed_files: {len(changed)}")
        for f in changed:
            print(f"  - {f}")
    print(f"fixed_bare_except: {stats['bare_except_fixed']}")
    print(f"fixed_utcnow: {stats['utcnow_fixed']}")
    print(f"remaining_bare_except_files: {len(remaining_bare)}")
    print(f"remaining_utcnow_files: {len(remaining_utc)}")

    if remaining_bare:
        print("REMAINING bare except in:")
        for f in remaining_bare:
            print(f"  - {f}")
    if remaining_utc:
        print("REMAINING utcnow in:")
        for f in remaining_utc:
            print(f"  - {f}")

    if args.check and (remaining_bare or remaining_utc):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
