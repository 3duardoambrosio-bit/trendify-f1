from __future__ import annotations
from pathlib import Path

p = Path("core/ledger.py")
src = p.read_text(encoding="utf-8")

# Patch only if we find a plain write without flush/fsync.
# We look for "f.write(" inside append() and insert flush+fsync right after.
if "def append(" not in src or "f.write(" not in src:
    raise SystemExit("ledger.py not recognized; aborting for safety")

if "f.flush()" in src or "os.fsync" in src:
    print("ledger already has flush/fsync; no-op")
    raise SystemExit(0)

if "import os" not in src:
    src = src.replace("import json", "import json\nimport os", 1)

marker = "f.write(line + \"\\n\")"
if marker not in src:
    raise SystemExit("write marker not found; aborting for safety")

src = src.replace(marker, marker + "\n            f.flush()\n            os.fsync(f.fileno())", 1)

p.write_text(src, encoding="utf-8")
print("patched core/ledger.py: added flush+fsync")