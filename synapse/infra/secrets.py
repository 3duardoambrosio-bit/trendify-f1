# synapse/infra/secrets.py
"""
Secrets — OLEADA 16
===================

- Carga .env (si existe) + os.environ (gana ENV).
- No imprime secretos.
- require_secret para fallar rápido cuando falte algo.

Uso:
from synapse.infra.secrets import Secrets

s = Secrets()
token = s.require("META_TOKEN")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


class SecretMissing(Exception):
    pass


def _parse_dotenv(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


@dataclass
class Secrets:
    dotenv_path: Path = Path(".env")

    def _dotenv(self) -> Dict[str, str]:
        if self.dotenv_path.exists():
            return _parse_dotenv(self.dotenv_path.read_text(encoding="utf-8", errors="replace"))
        return {}

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # ENV gana
        if key in os.environ:
            return os.environ.get(key)
        env = self._dotenv()
        return env.get(key, default)

    def require(self, key: str) -> str:
        v = self.get(key)
        if v is None or str(v).strip() == "":
            raise SecretMissing(f"Missing secret: {key}")
        return str(v)

    def masked(self, key: str) -> str:
        v = self.get(key)
        if not v:
            return "<missing>"
        s = str(v)
        if len(s) <= 6:
            return "***"
        return s[:2] + "***" + s[-2:]
