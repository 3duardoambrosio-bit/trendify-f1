from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict

__MARKER__ = "RUN_FINGERPRINT_2026-01-16_V1"


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_text(raw)


@dataclass(frozen=True)
class RunFingerprint:
    marker: str
    fingerprint: str         # sha256:<64>
    fingerprint_12: str      # first 12 chars (for logs)
    payload: Dict[str, Any]  # what was hashed (safe, no secrets)


def compute_run_fingerprint(*, plan_hash: str, runtime_snapshot: Dict[str, Any]) -> RunFingerprint:
    """
    Crea una identidad estable para una corrida:
      fingerprint = sha256(plan_hash + runtime_snapshot)
    runtime_snapshot debe ser SAFE (no tokens/secretos).
    """
    payload = {
        "plan_hash": str(plan_hash or ""),
        "runtime_snapshot": runtime_snapshot or {},
    }
    h = _sha256_obj(payload)
    fp = f"sha256:{h}"
    return RunFingerprint(
        marker=__MARKER__,
        fingerprint=fp,
        fingerprint_12=h[:12],
        payload=payload,
    )
