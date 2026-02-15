"""Append-only NDJSON ledger with stable API for scaffold. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _now_iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Ledger:
    """
    Minimal ledger with a deterministic, stable API:
      - Ledger.open(path)
      - append(event_type, correlation_id, idempotency_key, severity, payload)
    NDJSON format: 1 JSON object per line.
    """
    path: Path

    @staticmethod
    def open(path: str | Path) -> "Ledger":
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("", encoding="utf-8")
        return Ledger(path=p)

    def append(
        self,
        event_type: str,
        correlation_id: str,
        idempotency_key: str,
        severity: str = "INFO",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        rec = {
            "ts": _now_iso_utc(),
            "event_type": str(event_type),
            "correlation_id": str(correlation_id),
            "idempotency_key": str(idempotency_key),
            "severity": str(severity),
            "payload": payload or {},
        }
        line = json.dumps(rec, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
