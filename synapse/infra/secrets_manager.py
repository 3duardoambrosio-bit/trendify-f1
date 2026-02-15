"""Secrets manager (env-only) with fail-fast. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict, Iterable

class MissingSecretError(RuntimeError):
    pass

@dataclass(frozen=True)
class Secrets:
    values: Dict[str, str]

    def get(self, key: str) -> str:
        if key not in self.values or not self.values[key]:
            raise MissingSecretError(f"MISSING_SECRET={key}")
        return self.values[key]

def load_required(required: Iterable[str]) -> Secrets:
    req = list(required)
    out: Dict[str, str] = {}
    missing = []
    for k in req:
        v = os.environ.get(k, "")
        if not v:
            missing.append(k)
        else:
            out[k] = v
    if missing:
        raise MissingSecretError("MISSING_SECRET=" + ",".join(missing))
    return Secrets(values=out)
