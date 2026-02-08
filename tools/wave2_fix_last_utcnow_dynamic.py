from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

def run_audit() -> dict:
    # source of truth: audit_f1 stdout JSON
    p = subprocess.run(["python", "tools/audit_f1.py"], capture_output=True, text=True)
    out = p.stdout.strip()
    if not out.startswith("{"):
        raise SystemExit(f"AUDIT_STDOUT_NOT_JSON len={len(out)} stderr={p.stderr[-200:]}")
    return json.loads(out)

def must(condition: bool, msg: str) -> None:
    if not condition:
        raise SystemExit(msg)

def parse_sample(s: str) -> tuple[Path, int, str]:
    # format: path:line:code
    a, b, c = s.split(":", 2)
    return Path(a), int(b), c

def ensure_import_line(text: str, import_line: str) -> str:
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
    return ensure_import_line(text, "from datetime import timezone")

def patch_line(line: str) -> str:
    original = line

    # datetime.utcnow().isoformat()
    line = re.sub(
        r"datetime\.utcnow\(\)\.isoformat\(\)",
        "datetime.now(timezone.utc).isoformat().replace('+00:00','Z')",
        line,
    )

    # datetime.utcnow()
    line = re.sub(
        r"datetime\.utcnow\(\)",
        "datetime.now(timezone.utc)",
        line,
    )

    # isoformat() + "Z" -> isoformat().replace(...)
    line = re.sub(
        r"\.isoformat\(\)\s*\+\s*\"Z\"",
        ".isoformat().replace('+00:00','Z')",
        line,
    )

    # replace(microsecond=0).isoformat() + "Z" -> ...replace(...)
    line = re.sub(
        r"\.replace\(microsecond=0\)\.isoformat\(\)\s*\+\s*\"Z\"",
        ".replace(microsecond=0).isoformat().replace('+00:00','Z')",
        line,
    )

    return line if line != original else original

def main() -> int:
    d = run_audit()
    # locate utcnow_prod check
    uc = None
    for c in d.get("checks", []):
        if c.get("name") == "utcnow_prod":
            uc = c
            break
    must(uc is not None, "NO_UTCNOW_CHECK_FOUND")
    must(int(uc.get("count", 0)) == 1, f"EXPECTED_UTCNOW_COUNT_1 got={uc.get('count')}")
    samples = uc.get("sample", [])
    must(len(samples) >= 1, "NO_UTCNOW_SAMPLE")

    path, ln, _ = parse_sample(samples[0])
    must(path.exists(), f"MISSING_FILE::{path.as_posix()}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(True)
    must(1 <= ln <= len(lines), f"BAD_LINE_NO::{ln} max={len(lines)}")

    before = lines[ln - 1]
    after = patch_line(before)
    must(after != before, f"PATCH_NOOP::{path.as_posix()}:{ln}")

    lines[ln - 1] = after
    new_text = "".join(lines)

    # if we introduced timezone.utc OR datetime.now(timezone.utc), ensure timezone import
    if "timezone.utc" in new_text or "now(timezone.utc)" in new_text:
        new_text = ensure_from_datetime_timezone(new_text)

    path.write_text(new_text, encoding="utf-8")

    print(f"wave2_patched=1 file={path.as_posix()} line={ln}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())