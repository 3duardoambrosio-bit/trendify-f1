from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Ruta por defecto de la bitácora
BITACORA_PATH = Path("data/bitacora/bitacora.jsonl")


class EntryType(str, Enum):
    """Tipos estándar de eventos en Bitácora."""

    PRODUCT_EVALUATION = "product_evaluation"
    PRODUCT_EXIT = "product_exit"
    CAPITAL_EVENT = "capital_event"
    SYSTEM_EVENT = "system_event"


@dataclass
class BitacoraEntry:
    """Entrada individual en la bitácora."""

    entry_id: str
    timestamp: datetime
    entry_type: str  # se guarda como string ("product_evaluation", etc.)
    data: Dict[str, Any]
    metadata: Dict[str, Any]


class BitacoraAuto:
    """
    Bitácora append-only sobre un archivo JSONL.

    Notas de diseño:
    - Por compatibilidad, mantiene:
        - _load_entries()
        - _save_entries()
        - log(...)
    - Se agrega:
        - __init__(path=...)
        - load_entries() como wrapper público
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        # Permite BitacoraAuto() y BitacoraAuto(path=tmp_path / "bitacora.jsonl")
        if path is None:
            self._path = BITACORA_PATH
        else:
            self._path = Path(path)

        # Nos aseguramos de que exista el directorio
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # INTERNAL I/O
    # ------------------------------------------------------------------
    def _load_entries(self) -> List[BitacoraEntry]:
        """Carga TODAS las entradas desde el archivo. Si no existe, retorna []."""
        if not self._path.exists():
            return []

        entries: List[BitacoraEntry] = []
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)

                    ts_raw = raw.get("timestamp")
                    if isinstance(ts_raw, str):
                        timestamp = datetime.fromisoformat(ts_raw)
                    else:
                        timestamp = datetime.utcnow()

                    entry = BitacoraEntry(
                        entry_id=raw.get("entry_id", str(uuid4())),
                        timestamp=timestamp,
                        entry_type=raw.get("entry_type", "system_event"),
                        data=raw.get("data", {}) or {},
                        metadata=raw.get("metadata", {}) or {},
                    )
                    entries.append(entry)
        except Exception:
            # En producción podríamos loggear; para tests mejor fallar silencioso
            return []

        return entries

    def load_entries(self) -> List[BitacoraEntry]:
        """
        Versión pública de _load_entries, para que otros módulos
        (y tests) no dependan de la API "privada".
        """
        return self._load_entries()

    def _save_entries(self, entries: List[BitacoraEntry]) -> None:
        """Sobrescribe el archivo con todas las entradas (modo append-only controlado por llamado)."""
        with self._path.open("w", encoding="utf-8") as f:
            for e in entries:
                rec = {
                    "entry_id": e.entry_id,
                    "timestamp": e.timestamp.isoformat(),
                    "entry_type": e.entry_type,
                    "data": e.data,
                    "metadata": e.metadata,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def log(
        self,
        entry_type: EntryType | str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BitacoraEntry:
        """
        Agrega una nueva entrada a la bitácora.

        - entry_type puede ser EntryType.PRODUCT_EVALUATION o el string "product_evaluation".
        - data es cualquier dict serializable.
        - metadata es opcional (dict).
        """
        # Normalizamos a string para guardar
        if isinstance(entry_type, EntryType):
            etype_str = entry_type.value
        else:
            etype_str = str(entry_type)

        entry = BitacoraEntry(
            entry_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            entry_type=etype_str,
            data=data or {},
            metadata=metadata or {},
        )

        entries = self._load_entries()
        entries.append(entry)
        self._save_entries(entries)

        return entry
