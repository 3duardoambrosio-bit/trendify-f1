from __future__ import annotations

"""
Repo Hygiene  S15

Objetivo:
- Evitar flakiness y errores de colección de pytest por staging/pack dirs.
- Detectar basura peligrosa (tests/py) dentro de _incoming o packs temporales.

Principio: si hay staging con .py dentro del repo, eso puede romper el gate.
Por default:
- _incoming/  => PROHIBIDO si contiene .py
- S13/S14/S15 => PROHIBIDO si existen como carpetas (packs de sesión NO viven en el repo)

__MARKER__ embedded in module constant below.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import deal

__MARKER__ = "SESSION_S15_repo_hygiene_2026-03-03"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepoHygieneConfig:
    banned_root_dirs: Tuple[str, ...] = ("S13", "S14", "S15")
    incoming_dir: str = "_incoming"
    py_ext: str = ".py"


@dataclass(frozen=True)
class RepoHygieneResult:
    ok: bool
    errors: List[str]
    findings: Dict[str, List[str]]


def _find_py_files(root: Path, max_hits: int = 50) -> List[str]:
    hits: List[str] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".py":
            hits.append(str(p))
            if len(hits) >= max_hits:
                break
    return hits


@deal.pre(lambda repo_root, cfg=None: isinstance(repo_root, str) and repo_root.strip() != "")
@deal.post(lambda result: isinstance(result, RepoHygieneResult))
def scan_repo_hygiene(repo_root: str, cfg: Optional[RepoHygieneConfig] = None) -> RepoHygieneResult:
    cfg = cfg or RepoHygieneConfig()
    root = Path(repo_root)

    errors: List[str] = []
    findings: Dict[str, List[str]] = {}

    if not root.exists() or not root.is_dir():
        return RepoHygieneResult(False, ["repo_root_not_found"], {})

    # 1) banned session pack dirs at root
    for d in cfg.banned_root_dirs:
        p = root / d
        if p.exists() and p.is_dir():
            errors.append(f"banned_root_dir_present:{d}")
            findings[d] = [str(p)]

    # 2) incoming staging: allowed to exist, BUT must not contain .py
    inc = root / cfg.incoming_dir
    if inc.exists() and inc.is_dir():
        py_hits = _find_py_files(inc)
        if py_hits:
            errors.append("incoming_contains_py_files")
            findings[cfg.incoming_dir] = py_hits

    ok = len(errors) == 0
    return RepoHygieneResult(ok, errors, findings)
