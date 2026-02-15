"""File-backed idempotency store (JSON). AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

@dataclass
class IdempotencyStore:
    path: Path
    _data: Dict[str, str]

    @staticmethod
    def open(path: str | Path) -> "IdempotencyStore":
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8") or "{}")
        else:
            raw = {}
            p.write_text("{}", encoding="utf-8")
        if not isinstance(raw, dict):
            raise ValueError("idempotency_store_corrupt")
        return IdempotencyStore(path=p, _data={str(k): str(v) for k, v in raw.items()})

    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, value: str) -> None:
        self._data[key] = value
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
