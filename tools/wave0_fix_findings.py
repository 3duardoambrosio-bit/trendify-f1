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
    # If file already has "from datetime import X", append timezone.
    m = re.search(r"^(?P<ind>\s*)from\s+datetime\s+import\s+(?P<body>.+)\s*$", text, re.M)
    if m and "timezone" not in m.group("body"):
        body = m.group("body").rstrip()
        return text[:m.start()] + f"{m.group('ind')}from datetime import {body}, timezone" + text[m.end():]
    if re.search(r"^\s*from\s+datetime\s+import\s+timezone\s*$", text, re.M):
        return text
    return ensure_import(text, "from datetime import timezone")

def patch_infra_result() -> None:
    p = Path("infra/result.py")
    t = p.read_text(encoding="utf-8")

    # kill 2 prints -> logging.debug (no stdout)
    t = ensure_import(t, "import logging")
    if "log = logging.getLogger(__name__)" not in t:
        # add log=... right after imports block (safe-ish)
        t = re.sub(r"(^import\s+logging\s*$)", r"\1\n\nlog = logging.getLogger(__name__)\n", t, flags=re.M)

    t = must_sub(t, r"^\s*print\(\s*r\.value\s*\)\s*$", "log.debug('%s', r.value)", 1, "infra/result.py print(r.value)")
    t = must_sub(t, r"^\s*print\(\s*r\.error\s*\)\s*$", "log.debug('%s', r.error)", 1, "infra/result.py print(r.error)")

    p.write_text(t, encoding="utf-8")

def patch_learning_loop() -> None:
    p = Path("synapse/learning/learning_loop.py")
    t = p.read_text(encoding="utf-8")

    t = must_sub(
        t,
        r"datetime\.datetime\.utcnow\(\)",
        "datetime.datetime.now(datetime.timezone.utc)",
        1,
        "learning_loop utcnow()",
    )
    t = must_sub(
        t,
        r"\.replace\(microsecond=0\)\.isoformat\(\)\s*\+\s*\"Z\"",
        ".replace(microsecond=0).isoformat().replace('+00:00','Z')",
        1,
        "learning_loop Z suffix",
    )
    p.write_text(t, encoding="utf-8")

def patch_market_pulse() -> None:
    p = Path("synapse/pulse/market_pulse.py")
    t = p.read_text(encoding="utf-8")

    t = must_sub(
        t,
        r"_dt\.datetime\.utcnow\(\)",
        "_dt.datetime.now(_dt.timezone.utc)",
        1,
        "market_pulse utcnow()",
    )
    t = must_sub(
        t,
        r"\.replace\(microsecond=0\)\.isoformat\(\)\s*\+\s*\"Z\"",
        ".replace(microsecond=0).isoformat().replace('+00:00','Z')",
        1,
        "market_pulse Z suffix",
    )
    p.write_text(t, encoding="utf-8")

def patch_safety_audit() -> None:
    p = Path("synapse/safety/audit.py")
    t = p.read_text(encoding="utf-8")

    # line sample: "timestamp": datetime.utcnow().isoformat(),
    # -> "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    t = ensure_from_datetime_timezone(t)
    t = must_sub(
        t,
        r"datetime\.utcnow\(\)\.isoformat\(\)",
        "datetime.now(timezone.utc).isoformat().replace('+00:00','Z')",
        1,
        "safety/audit utcnow().isoformat()",
    )
    p.write_text(t, encoding="utf-8")

def patch_bitacora_auto() -> None:
    p = Path("infra/bitacora_auto.py")
    t = p.read_text(encoding="utf-8")

    t = ensure_from_datetime_timezone(t)
    # Replace EXACT 3 occurrences flagged by audit
    t = must_sub(
        t,
        r"datetime\.utcnow\(\)",
        "datetime.now(timezone.utc)",
        3,
        "bitacora_auto datetime.utcnow()",
    )
    p.write_text(t, encoding="utf-8")

def main() -> int:
    patch_infra_result()
    patch_learning_loop()
    patch_market_pulse()
    patch_safety_audit()
    patch_bitacora_auto()
    print("wave0_patched=1 files=5")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())