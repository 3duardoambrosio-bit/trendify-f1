"""Feature flags via environment variables. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict

def _parse_bool(v: str) -> bool:
    v = v.strip().lower()
    return v in ("1","true","yes","y","on")

@dataclass(frozen=True)
class FeatureFlags:
    values: Dict[str, bool]

    @staticmethod
    def load(prefix: str = "SYNAPSE_FLAG_") -> "FeatureFlags":
        out: Dict[str, bool] = {}
        for k, v in os.environ.items():
            if k.startswith(prefix):
                name = k[len(prefix):].strip().lower()
                out[name] = _parse_bool(v)
        return FeatureFlags(values=out)

    def is_on(self, name: str, default: bool = False) -> bool:
        return self.values.get(name.strip().lower(), default)
