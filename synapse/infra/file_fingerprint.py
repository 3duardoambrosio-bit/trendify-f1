from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FILE_REF_RE = re.compile(r"^<FILE:([^>]+)>$")


def _sha256_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _safe_abs(path_str: str, *, cwd: Path) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (cwd / p).resolve()
    else:
        p = p.resolve()
    return p


def _collect_file_refs_from_obj(obj: Any) -> List[str]:
    out: List[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            m = FILE_REF_RE.match(x.strip())
            if m:
                out.append(m.group(1))

    walk(obj)

    # dedupe stable
    seen = set()
    uniq: List[str] = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


def collect_file_paths_from_steps(steps: List[Dict[str, Any]]) -> List[str]:
    refs: List[str] = []
    for s in steps:
        payload = s.get("payload", {})
        refs.extend(_collect_file_refs_from_obj(payload))

    # dedupe stable
    seen = set()
    uniq: List[str] = []
    for r in refs:
        if r in seen:
            continue
        seen.add(r)
        uniq.append(r)
    return uniq


def compute_file_fingerprints_from_steps(
    steps: List[Dict[str, Any]],
    *,
    cwd: Optional[Path] = None,
    algo: str = "sha256",
) -> Dict[str, Any]:
    """
    Devuelve un snapshot determinista para meter en runtime_snapshot.
    - NO imprime secretos.
    - Si falta archivo: marca missing=True, sha256=""
    """
    cwd2 = cwd or Path.cwd()
    file_refs = collect_file_paths_from_steps(steps)

    entries: Dict[str, Dict[str, Any]] = {}
    for ref in file_refs:
        p = _safe_abs(ref, cwd=cwd2)
        key = str(p)

        if p.exists() and p.is_file():
            st = p.stat()
            sha = _sha256_file(p) if algo == "sha256" else ""
            entries[key] = {
                "missing": False,
                "size": int(st.st_size),
                "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))),
                "sha256": sha,
                "sha256_12": sha[:12] if sha else "",
            }
        else:
            entries[key] = {
                "missing": True,
                "size": 0,
                "mtime_ns": 0,
                "sha256": "",
                "sha256_12": "",
            }

    # hash global determinista
    material = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    overall = hashlib.sha256(material.encode("utf-8")).hexdigest()

    return {
        "algo": algo,
        "count": len(entries),
        "missing": sum(1 for v in entries.values() if v.get("missing")),
        "overall_sha256": overall,
        "overall_sha12": overall[:12],
        "entries": entries,  # path abs -> meta
    }
