from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

__MARKER__ = "META_PUBLISH_LEDGER_2026-01-16_V2"


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _write_json_atomic(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _append_ndjson(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class LedgerDriftError(RuntimeError):
    pass


@dataclass(frozen=True)
class LedgerConfig:
    dir: Path
    map_json: Path
    events_ndjson: Path


def default_config(dir_path: str | Path = "data/ledger") -> LedgerConfig:
    d = Path(dir_path).resolve()
    return LedgerConfig(
        dir=d,
        map_json=d / "meta_publish_map.json",
        events_ndjson=d / "meta_publish_events.ndjson",
    )


class MetaPublishLedger:
    """
    Ledger idempotente (scoped por RUN):
      - key_compuesta = f"{run_fingerprint}|{step_key}"
      - guarda created_id + payload_sha256 + endpoint_resolved + op
      - rerun mismo run_fingerprint => REUSED
      - drift dentro del mismo run => FAIL por seguridad
    """

    def __init__(self, *, run_fingerprint: str, plan_hash: str, cfg: LedgerConfig):
        self.run_fingerprint = str(run_fingerprint or "")
        self.plan_hash = str(plan_hash or "")
        self.cfg = cfg
        self._map = _read_json(cfg.map_json)

    def _k(self, step_key: str) -> str:
        return f"{self.run_fingerprint}|{step_key}"

    def payload_hash(self, payload_resolved: Dict[str, Any]) -> str:
        return _sha256_obj(payload_resolved)

    def get(self, step_key: str) -> Optional[Dict[str, Any]]:
        return self._map.get(self._k(step_key))

    def reuse_or_raise_drift(
        self,
        *,
        step_key: str,
        op: str,
        endpoint_resolved: str,
        payload_sha256: str,
    ) -> Optional[str]:
        rec = self.get(step_key)
        if not rec:
            return None

        same_op = (rec.get("op") == op)
        same_ep = (rec.get("endpoint_resolved") == endpoint_resolved)
        same_payload = (rec.get("payload_sha256") == payload_sha256)

        if same_op and same_ep and same_payload:
            return str(rec.get("id") or "")

        raise LedgerDriftError(
            "ledger_drift for step_key="
            + step_key
            + " (existing id="
            + str(rec.get("id"))
            + ")\n"
            + "Expected same op/endpoint/payload within SAME run_fingerprint.\n"
            + f"- run_fingerprint: {self.run_fingerprint[:20]}...\n"
            + f"- op: {rec.get('op')} != {op}\n"
            + f"- endpoint: {rec.get('endpoint_resolved')} != {endpoint_resolved}\n"
            + f"- payload_sha256: {str(rec.get('payload_sha256'))[:12]} != {payload_sha256[:12]}\n"
        )

    def commit(
        self,
        *,
        step_key: str,
        op: str,
        endpoint_resolved: str,
        payload_sha256: str,
        created_id: str,
        response_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = self._k(step_key)
        rec = {
            "marker": __MARKER__,
            "ts": _utc_now_z(),
            "run_fingerprint": self.run_fingerprint,
            "plan_hash": self.plan_hash,
            "step_key": step_key,
            "op": op,
            "endpoint_resolved": endpoint_resolved,
            "payload_sha256": payload_sha256,
            "id": str(created_id),
        }
        self._map[key] = rec
        _write_json_atomic(self.cfg.map_json, self._map)

        ev = dict(rec)
        if response_meta:
            ev["response_meta"] = response_meta  # safe summary only
        _append_ndjson(self.cfg.events_ndjson, ev)
