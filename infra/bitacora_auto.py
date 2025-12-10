from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# Ruta por defecto de la bitácora en producción
BITACORA_PATH = Path(os.getenv("BITACORA_PATH", "data/bitacora/bitacora.jsonl"))


class EntryType(str, Enum):
    PRODUCT_EVALUATION = "product_evaluation"
    PRODUCT_EXIT = "product_exit"
    CAPITAL_EVENT = "capital_event"
    HYPOTHESIS_EVENT = "hypothesis_event"


@dataclass
class BitacoraEntry:
    entry_id: str
    timestamp: datetime
    entry_type: EntryType
    data: Dict[str, Any]
    metadata: Dict[str, Any]


class BitacoraAuto:
    """
    Bitácora append-only en formato JSONL.

    Reglas:
    - Siempre escribe en self._path.
    - Siempre que se llama load_entries(), recarga desde disco.
    - entry_type SIEMPRE se normaliza a EntryType.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path: Path = path or BITACORA_PATH
        self._entries: List[BitacoraEntry] = []
        self._load_entries()

    # -----------------------------
    # Helpers internos
    # -----------------------------

    @staticmethod
    def _parse_entry_type(raw: Any) -> EntryType:
        """
        Normaliza lo que venga (str, Enum, lo que sea) a EntryType.
        Soporta datos viejos donde se guardó el string plano.
        """
        if isinstance(raw, EntryType):
            return raw
        if isinstance(raw, str):
            try:
                return EntryType(raw)
            except ValueError:
                # Fallback seguro: tratamos lo desconocido como evaluación
                return EntryType.PRODUCT_EVALUATION
        return EntryType.PRODUCT_EVALUATION

    def _load_entries(self) -> None:
        """Recarga todo desde disco a memoria."""
        self._entries = []

        # Asegura carpeta
        self._path.parent.mkdir(parents=True, exist_ok=True)

        if not self._path.exists():
            return

        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                raw = json.loads(line)
                ts_raw = raw.get("timestamp")

                if isinstance(ts_raw, str):
                    try:
                        ts = datetime.fromisoformat(ts_raw)
                    except ValueError:
                        ts = datetime.utcnow()
                else:
                    ts = datetime.utcnow()

                entry_type = self._parse_entry_type(raw.get("entry_type"))

                entry = BitacoraEntry(
                    entry_id=str(raw.get("entry_id")),
                    timestamp=ts,
                    entry_type=entry_type,
                    data=raw.get("data") or {},
                    metadata=raw.get("metadata") or {},
                )
                self._entries.append(entry)

    def load_entries(self) -> List[BitacoraEntry]:
        """
        API pública usada por tests y sistemas:
        siempre recarga desde disco y devuelve una copia de la lista.
        """
        self._load_entries()
        return list(self._entries)

    def _save_entries(self) -> None:
        """Persiste TODAS las entradas actuales a disco."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        with self._path.open("w", encoding="utf-8") as f:
            for e in self._entries:
                record = {
                    "entry_id": e.entry_id,
                    "timestamp": e.timestamp.isoformat(),
                    "entry_type": e.entry_type.value,
                    "data": e.data,
                    "metadata": e.metadata,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -----------------------------
    # API pública principal
    # -----------------------------

    def log(
        self,
        entry_type: EntryType,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BitacoraEntry:
        """
        Agrega una nueva entrada y la persiste.

        entry_type: siempre se normaliza a EntryType.
        """
        from uuid import uuid4

        entry = BitacoraEntry(
            entry_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            entry_type=self._parse_entry_type(entry_type),
            data=data or {},
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._save_entries()
        return entry
    # Singleton de conveniencia para código legacy
# Usa el BITACORA_PATH por defecto.
bitacora = BitacoraAuto()

