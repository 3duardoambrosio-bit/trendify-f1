from __future__ import annotations

from pathlib import Path
from typing import Dict


def parse_env_text(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()

        # strip quotes
        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]

        if k:
            out[k] = v
    return out


def load_env_file(path: str | Path, *, override: bool = False) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    data = parse_env_text(p.read_text(encoding="utf-8"))
    import os
    for k, v in data.items():
        if override or (k not in os.environ) or (os.environ.get(k, "") == ""):
            os.environ[k] = v
    return data
