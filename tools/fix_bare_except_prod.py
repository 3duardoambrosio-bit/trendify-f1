from __future__ import annotations

import re
from pathlib import Path

PROD_DIRS = [Path("synapse"), Path("infra"), Path("ops"), Path("buyer"), Path("core"), Path("config")]

RX = re.compile(r"(?m)^(?P<indent>[ \t]*)except[ \t]*:[ \t]*$")

def main() -> int:
    changed_files = 0
    changed_hits = 0

    for root in PROD_DIRS:
        if not root.exists():
            continue
        for fp in root.rglob("*.py"):
            text = fp.read_text(encoding="utf-8")
            new_text, n = RX.subn(r"\g<indent>except Exception:", text)
            if n:
                fp.write_text(new_text, encoding="utf-8")
                changed_files += 1
                changed_hits += n

    print(f"changed_files={changed_files}")
    print(f"changed_hits={changed_hits}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())