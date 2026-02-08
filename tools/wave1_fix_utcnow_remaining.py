from __future__ import annotations

import re
from pathlib import Path

def must_sub(text: str, pattern: str, repl: str, expected: int, label: str) -> str:
    new, n = re.subn(pattern, repl, text, flags=re.M)
    if n != expected:
        raise SystemExit(f"PATCH_ABORT::{label} expected={expected} got={n}")
    return new

def ensure_import(text: str, import_line: str) -> str:
    if re.search(rf"^\s*{re.escape(import_line)}\s*$", text, re.M):
        return text
    lines = text.splitlines(True)
    i = 0
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    if i < len(lines) and "coding" in lines[i]:
        i += 1
    while i < len(lines) and lines[i].startswith("from __future__ import"):
        i += 1
    if i < len(lines) and lines[i].strip() != "":
        lines.insert(i, "\n"); i += 1
    lines.insert(i, import_line + "\n")
    return "".join(lines)

def ensure_from_datetime_timezone(text: str) -> str:
    # append timezone to existing "from datetime import ..."
    m = re.search(r"^(?P<ind>\s*)from\s+datetime\s+import\s+(?P<body>.+)\s*$", text, re.M)
    if m and "timezone" not in m.group("body"):
        body = m.group("body").rstrip()
        return text[:m.start()] + f"{m.group('ind')}from datetime import {body}, timezone" + text[m.end():]
    if re.search(r"^\s*from\s+datetime\s+import\s+timezone\s*$", text, re.M):
        return text
    return ensure_import(text, "from datetime import timezone")

def patch_blindaje() -> None:
    p = Path("infra/blindaje.py")
    t = p.read_text(encoding="utf-8")
    t = ensure_from_datetime_timezone(t)

    # 4 occurrences: datetime.utcnow().isoformat()
    t = must_sub(
        t,
        r"datetime\.utcnow\(\)\.isoformat\(\)",
        "datetime.now(timezone.utc).isoformat().replace('+00:00','Z')",
        4,
        "blindaje utcnow().isoformat()",
    )
    p.write_text(t, encoding="utf-8")

def patch_dropi_product_finder() -> None:
    p = Path("ops/dropi_product_finder.py")
    t = p.read_text(encoding="utf-8")
    t = ensure_from_datetime_timezone(t)

    # 2 occurrences: datetime.utcnow().strftime(...)
    t = must_sub(
        t,
        r"datetime\.utcnow\(\)",
        "datetime.now(timezone.utc)",
        2,
        "dropi_product_finder utcnow()",
    )
    p.write_text(t, encoding="utf-8")

def patch_enrich_candidates_f1() -> None:
    p = Path("ops/enrich_candidates_f1.py")
    t = p.read_text(encoding="utf-8")
    t = ensure_from_datetime_timezone(t)

    # 1 occurrence: datetime.utcnow().isoformat() + "Z"
    t = must_sub(
        t,
        r"datetime\.utcnow\(\)",
        "datetime.now(timezone.utc)",
        1,
        "enrich_candidates_f1 utcnow()",
    )
    t = must_sub(
        t,
        r"\.isoformat\(\)\s*\+\s*\"Z\"",
        ".isoformat().replace('+00:00','Z')",
        1,
        "enrich_candidates_f1 Z suffix",
    )
    p.write_text(t, encoding="utf-8")

def patch_enrich_candidates_f1_v2() -> None:
    p = Path("ops/enrich_candidates_f1_v2.py")
    t = p.read_text(encoding="utf-8")
    t = ensure_from_datetime_timezone(t)

    # 3 occurrences of datetime.utcnow(): 1 strftime run_id + 2 isoformat+Z
    t = must_sub(
        t,
        r"datetime\.utcnow\(\)",
        "datetime.now(timezone.utc)",
        3,
        "enrich_candidates_f1_v2 utcnow()",
    )
    # 2 occurrences of isoformat()+ "Z" (generated_at + ts)
    t = must_sub(
        t,
        r"\.isoformat\(\)\s*\+\s*\"Z\"",
        ".isoformat().replace('+00:00','Z')",
        2,
        "enrich_candidates_f1_v2 Z suffix",
    )
    p.write_text(t, encoding="utf-8")

def patch_tribunal() -> None:
    p = Path("ops/systems/tribunal.py")
    t = p.read_text(encoding="utf-8")
    t = ensure_from_datetime_timezone(t)

    # 2 occurrences: else datetime.utcnow() + timestamp = datetime.utcnow()
    t = must_sub(
        t,
        r"datetime\.utcnow\(\)",
        "datetime.now(timezone.utc)",
        2,
        "tribunal utcnow()",
    )
    p.write_text(t, encoding="utf-8")

def main() -> int:
    patch_blindaje()
    patch_dropi_product_finder()
    patch_enrich_candidates_f1()
    patch_enrich_candidates_f1_v2()
    patch_tribunal()
    print("wave1_patched=1 files=5")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())