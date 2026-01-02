from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def stable_json_dumps(obj: Any) -> str:
    # Deterministic JSON string (sorted keys, compact separators)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(obj: Any) -> str:
    return sha256_text(stable_json_dumps(obj))


def file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def compute_hashes(paths: list[Path], *, base_dir: Path | None = None) -> dict[str, str]:
    """
    Return map: relative_or_name -> sha256
    """
    out: dict[str, str] = {}
    base = base_dir
    for p in paths:
        key = str(p)
        if base is not None:
            try:
                key = str(p.resolve().relative_to(base.resolve()))
            except Exception:
                key = str(p)
        out[key] = file_sha256(p)
    return out


@dataclass(frozen=True)
class SnapshotConfig:
    name: str
    schema_version: str
    include_timestamp: bool = True


def build_snapshot(
    *,
    config: SnapshotConfig,
    hashes: dict[str, str],
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": config.name,
        "schema_version": config.schema_version,
        "hashes": dict(sorted(hashes.items(), key=lambda kv: kv[0])),
        "meta": meta or {},
    }
    if config.include_timestamp:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()

    # self-hash for integrity (excluding itself)
    tmp = dict(payload)
    tmp.pop("self_hash", None)
    payload["self_hash"] = sha256_json(tmp)
    return payload


def write_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = stable_json_dumps(payload) + "\n"
    # UTF-8 without BOM by default
    path.write_text(data, encoding="utf-8", newline="\n")


def read_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
