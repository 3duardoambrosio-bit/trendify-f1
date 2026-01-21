from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse.infra.contract_snapshot import file_sha256, sha256_json, stable_json_dumps


@dataclass(frozen=True)
class Artifact:
    relpath: str
    sha256: str
    bytes: int


def artifact_from_file(path: Path, *, base_dir: Path) -> Artifact:
    rp = str(path.resolve().relative_to(base_dir.resolve()))
    return Artifact(relpath=rp, sha256=file_sha256(path), bytes=path.stat().st_size)


def build_manifest(
    *,
    product_id: str,
    schema_version: str,
    artifacts: list[Artifact],
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "product_id": product_id,
        "artifacts": [a.__dict__ for a in sorted(artifacts, key=lambda x: x.relpath)],
        "meta": meta or {},
    }
    tmp = dict(payload)
    tmp.pop("self_hash", None)
    payload["self_hash"] = sha256_json(tmp)
    return payload


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = stable_json_dumps(manifest) + "\n"
    path.write_text(data, encoding="utf-8", newline="\n")


def read_manifest(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
