from __future__ import annotations

import json
import os
import platform
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from synapse.infra.contract_snapshot import sha256_text, stable_json_dumps


@dataclass(frozen=True)
class CrashReport:
    fingerprint: str
    path: Path


_ENV_DIAG_DIR = "SYNAPSE_DIAG_DIR"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_sanitize(x: Any) -> Any:
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, (list, tuple)):
        return [_json_sanitize(i) for i in x]
    if isinstance(x, dict):
        out: dict[str, Any] = {}
        for k, v in x.items():
            out[str(k)] = _json_sanitize(v)
        return out
    return repr(x)


def exception_fingerprint(exc: BaseException) -> str:
    et = type(exc).__name__
    msg = str(exc)

    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ is not None else []
    sig_parts = [et, msg]
    for fr in frames[-12:]:
        sig_parts.append(f"{fr.filename}:{fr.lineno}:{fr.name}")
    sig = "|".join(sig_parts)
    return sha256_text(sig)


def resolve_diag_dir(default: str = r"data\ledger\errors") -> Path:
    p = os.getenv(_ENV_DIAG_DIR, default)
    return Path(p)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = stable_json_dumps(payload) + "\n"
    path.write_text(data, encoding="utf-8", newline="\n")


def _structured_frames(exc: BaseException) -> list[dict[str, Any]]:
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ is not None else []
    out: list[dict[str, Any]] = []
    for fr in frames[-20:]:
        out.append(
            {
                "file": fr.filename,
                "line": fr.lineno,
                "func": fr.name,
                "text": fr.line,
            }
        )
    return out


def suggest_fix(exc: BaseException) -> str | None:
    # Type-based hints
    if isinstance(exc, FileNotFoundError):
        m = str(exc).lower()
        if "canonical" in m or "catalog" in m:
            return "No se encontró el catálogo canonical. Pasa --canonical-csv <ruta> o guarda un CSV en data/ con columnas product_id/title."
        return "Falta un archivo. Revisa ruta/cwd. Si corres en otro cwd/CI, pasa rutas absolutas o usa --out-root."
    if isinstance(exc, KeyError):
        m = str(exc).lower()
        if "product_id" in m:
            return "El product_id no existe en el canonical CSV. Confirma que esté en el catálogo o usa otro product_id."
        return "Clave faltante en CSV/JSON. Revisa encabezados/nombres de campos."
    if isinstance(exc, AttributeError):
        if "no known entrypoint" in str(exc).lower():
            return "Módulo sin entrypoint invocable (run/main). Define run(**kwargs) o main(argv) para integrarlo al CLI."

    # Message-pattern hints (para casos como RuntimeError con msg específico)
    msg = (str(exc) or "").lower()
    if "canonical_csv not found" in msg or ("canonical" in msg and "not found" in msg):
        return "No se encontró canonical CSV. Solución rápida: --canonical-csv <ruta>. Solución permanente: asegúrate que exista un CSV bajo data/ con encabezados product_id,title."
    if "product_id not found" in msg:
        return "Tu product_id no está en el catálogo. Abre el canonical CSV y confirma el valor exacto (sin espacios)."
    if "permission" in msg and ("denied" in msg or "access" in msg):
        return "Tema permisos/lock. Cierra Excel/editores que tengan el CSV abierto y verifica que data/ledger sea writable."

    return None


def capture_exception(
    exc: BaseException,
    *,
    context: dict[str, Any] | None = None,
    diag_dir: Path | None = None,
) -> CrashReport:
    fp = exception_fingerprint(exc)
    out_dir = diag_dir or resolve_diag_dir()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"error_{ts}_{fp[:12]}.json"
    path = out_dir / name

    tb_txt = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    payload: dict[str, Any] = {
        "created_at": _utc_now(),
        "fingerprint": fp,
        "exception": {
            "type": type(exc).__name__,
            "message": str(exc),
            "repr": repr(exc),
        },
        "frames": _structured_frames(exc),
        "traceback": tb_txt,
        "hint": suggest_fix(exc),
        "runtime": {
            "python_version": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "cwd": os.getcwd(),
        },
        "argv": list(sys.argv),
        "context": _json_sanitize(context or {}),
        "env_whitelist": {
            "SYNAPSE_DEBUG": os.getenv("SYNAPSE_DEBUG"),
            "SYNAPSE_DEBUG_CLI": os.getenv("SYNAPSE_DEBUG_CLI"),
            _ENV_DIAG_DIR: os.getenv(_ENV_DIAG_DIR),
            "PYTHONPATH": os.getenv("PYTHONPATH"),
        },
    }

    _write_json(path, payload)
    return CrashReport(fingerprint=fp, path=path)


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_report(diag_dir: Path | None = None) -> Path | None:
    d = diag_dir or resolve_diag_dir()
    if not d.exists():
        return None
    files = sorted(d.glob("error_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None
