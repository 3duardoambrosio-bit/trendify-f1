# synapse/integration/secrets.py
"""
Secrets/Config Loader (stdlib) para SYNAPSE.

Objetivo:
- Centralizar env vars / .env sin meter librerías.
- Validación estricta (missing = error explícito).
- Masking para logs.

Nota:
- NO escribir secretos al ledger (jamás).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


class SecretsError(RuntimeError):
    pass


@dataclass(frozen=True)
class SecretSpec:
    key: str
    required: bool = True
    validator: Optional[Callable[[str], bool]] = None
    hint: str = ""


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


def _mask(value: str) -> str:
    if value is None:
        return ""
    s = str(value)
    if len(s) <= 4:
        return "***"
    return s[:2] + "***" + s[-2:]


class SecretsVault:
    def __init__(self, *, dotenv_path: str = ".env", allow_dotenv: bool = True):
        self.dotenv_path = dotenv_path
        self.allow_dotenv = allow_dotenv
        self._dotenv_cache: Dict[str, str] = {}

        if self.allow_dotenv and os.path.exists(self.dotenv_path):
            with open(self.dotenv_path, "r", encoding="utf-8") as f:
                self._dotenv_cache = _parse_dotenv(f.read())

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in os.environ:
            return os.environ.get(key)
        if self.allow_dotenv and key in self._dotenv_cache:
            return self._dotenv_cache.get(key)
        return default

    def require(self, key: str, hint: str = "") -> str:
        v = self.get(key)
        if v is None or str(v).strip() == "":
            msg = f"Missing secret: {key}"
            if hint:
                msg += f" | hint: {hint}"
            raise SecretsError(msg)
        return str(v)

    def validate(self, specs: Tuple[SecretSpec, ...]) -> Dict[str, str]:
        resolved: Dict[str, str] = {}
        for sp in specs:
            v = self.get(sp.key)
            if (v is None or str(v).strip() == "") and sp.required:
                raise SecretsError(f"Missing secret: {sp.key} | hint: {sp.hint}")
            if v is None:
                continue
            v = str(v)
            if sp.validator is not None and not sp.validator(v):
                raise SecretsError(f"Invalid secret: {sp.key} | hint: {sp.hint}")
            resolved[sp.key] = v
        return resolved

    def debug_masked(self, key: str) -> str:
        v = self.get(key, "")
        return _mask(v or "")
