from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

__MARKER__ = "SYNAPSE_BOOTSTRAP_ENV_2026-01-15_V1"


def _is_true(x: str) -> bool:
    return (x or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _find_repo_root(start: Path) -> Optional[Path]:
    """
    Heurística: buscamos .env.local o .git o pyproject.toml subiendo desde CWD.
    """
    start = start.resolve()
    for p in [start] + list(start.parents):
        if (p / ".env.local").exists():
            return p
        if (p / ".git").exists():
            return p
        if (p / "pyproject.toml").exists():
            return p
    return None


def bootstrap_env(env_filename: str = ".env.local") -> Dict[str, Any]:
    """
    Carga .env.local (si existe) a os.environ.
    - NO imprime secretos
    - NO revienta si falta
    - NO override a env vars ya seteadas
    """
    if _is_true(os.environ.get("SYNAPSE_DISABLE_ENVFILE", "")):
        os.environ.setdefault("SYNAPSE_ENVFILE_LOADED", "0")
        return {"status": "SKIP", "reason": "SYNAPSE_DISABLE_ENVFILE=1"}

    root = _find_repo_root(Path.cwd())
    if not root:
        os.environ.setdefault("SYNAPSE_ENVFILE_LOADED", "0")
        return {"status": "SKIP", "reason": "repo_root_not_found"}

    env_path = (root / env_filename).resolve()
    if not env_path.exists():
        os.environ.setdefault("SYNAPSE_ENVFILE_LOADED", "0")
        return {"status": "SKIP", "reason": f"{env_filename}_missing", "path": str(env_path)}

    try:
        from synapse.infra.envfile import load_env_file
        load_env_file(env_path, override=False)
        # bandera para confirmar que el hook corrió (aunque el archivo esté vacío)
        os.environ["SYNAPSE_ENVFILE_LOADED"] = "1"
        os.environ["SYNAPSE_ENVFILE_PATH"] = str(env_path)
        return {"status": "OK", "path": str(env_path)}
    except Exception as e:
        os.environ.setdefault("SYNAPSE_ENVFILE_LOADED", "0")
        return {"status": "FAIL", "error": f"{type(e).__name__}: {e}"}