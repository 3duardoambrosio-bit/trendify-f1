# infra/blindaje.py
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, List

from infra.logging_config import get_logger

logger = get_logger(__name__)


class LockType(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class LockStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"


@dataclass
class Lock:
    lock_id: str
    lock_type: LockType
    reason: str
    status: LockStatus = LockStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    released_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class Blindaje:
    """
    Módulo central de locks de SYNAPSE.

    Fase F0/F1:
    - Registro en memoria
    - Persistencia en JSONL
    - API mínima: activar, liberar, preguntar, listar
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        # Ruta por defecto para uso real
        self._storage_path = storage_path or Path("data/locks/locks.jsonl")
        self._locks: Dict[str, Lock] = {}
        self._ensure_dir()
        self._load_from_disk()

    # ---------- Infra básica ----------

    def _ensure_dir(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_from_disk(self) -> None:
        """Carga locks existentes desde JSONL, si hay."""
        if not self._storage_path.exists():
            return

        try:
            with self._storage_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)
                    lock = Lock(
                        lock_id=raw["lock_id"],
                        lock_type=LockType(raw["lock_type"]),
                        reason=raw["reason"],
                        status=LockStatus(raw.get("status", LockStatus.ACTIVE)),
                        created_at=raw.get("created_at")
                        or datetime.utcnow().isoformat(),
                        released_at=raw.get("released_at"),
                        metadata=raw.get("metadata", {}),
                    )
                    self._locks[lock.lock_id] = lock
        except Exception as exc:
            logger.error("Error loading locks from %s: %s", self._storage_path, exc)

    def _append_to_disk(self, lock: Lock) -> None:
        """Añade/reescribe un lock al archivo (append-only)."""
        try:
            with self._storage_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(lock), ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error(
                "Error writing lock %s to %s: %s",
                lock.lock_id,
                self._storage_path,
                exc,
            )

    def _rewrite_all(self) -> None:
        """
        Reescribe el archivo completo.

        Se usa cuando cambiamos estado (release) para mantener consistencia.
        """
        try:
            with self._storage_path.open("w", encoding="utf-8") as f:
                for lock in self._locks.values():
                    f.write(json.dumps(asdict(lock), ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("Error rewriting locks file %s: %s", self._storage_path, exc)

    # ---------- API pública ----------

    def activate_lock(
        self,
        lock_id: str,
        lock_type: LockType,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> Lock:
        """
        Activa un lock (o lo re-activa si ya existía).

        Idempotente a nivel de ID: último write gana.
        """
        metadata = metadata or {}
        lock = Lock(
            lock_id=lock_id,
            lock_type=lock_type,
            reason=reason,
            status=LockStatus.ACTIVE,
            created_at=datetime.utcnow().isoformat(),
            released_at=None,
            metadata=metadata,
        )
        self._locks[lock_id] = lock
        self._append_to_disk(lock)
        logger.info("Lock activado: %s (%s) - %s", lock_id, lock_type.value, reason)
        return lock

    def release_lock(self, lock_id: str, reason: Optional[str] = None) -> Optional[Lock]:
        """
        Marca un lock como RELEASED. No borra historial, solo cambia estado.
        """
        lock = self._locks.get(lock_id)
        if not lock:
            return None

        lock.status = LockStatus.RELEASED
        lock.released_at = datetime.utcnow().isoformat()
        if reason:
            lock.metadata.setdefault("release_reason", reason)

        self._rewrite_all()
        logger.info("Lock liberado: %s", lock_id)
        return lock

    def is_locked(self, lock_id: str) -> bool:
        """True si el lock existe y sigue activo."""
        lock = self._locks.get(lock_id)
        return bool(lock and lock.status == LockStatus.ACTIVE)

    def get_lock(self, lock_id: str) -> Optional[Lock]:
        """Devuelve el lock completo si existe."""
        return self._locks.get(lock_id)

    def list_active_locks(self) -> List[Lock]:
        """Lista solo locks activos."""
        return [l for l in self._locks.values() if l.status == LockStatus.ACTIVE]

    def list_all_locks(self) -> List[Lock]:
        """Lista todos los locks, activos y liberados."""
        return list(self._locks.values())


# Instancia global para uso en el resto del sistema
blindaje = Blindaje()
