# infra/bitacora_auto.py

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from infra.logging_config import get_logger

logger = get_logger(__name__)


from enum import Enum

class EntryType(str, Enum):
    PRODUCT_EVALUATION = "product_evaluation"
    CAPITAL_SPEND = "capital_spend"
    PRODUCT_EXIT = "product_exit"  # NEW




@dataclass
class BitacoraEntry:
    entry_id: str
    timestamp: str  # ISO 8601
    entry_type: EntryType
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "entry_type": self.entry_type.value,
            "data": self.data,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "BitacoraEntry":
        # entry_type puede venir como string simple
        raw_type = raw.get("entry_type", EntryType.SYSTEM.value)
        try:
            entry_type = EntryType(raw_type)
        except ValueError:
            logger.warning(
                "Unknown bitácora entry_type, using SYSTEM as fallback",
                extra={"extra_data": {"entry_type": raw_type}},
            )
            entry_type = EntryType.SYSTEM

        timestamp = raw.get("timestamp")
        if not timestamp:
            timestamp = datetime.utcnow().isoformat()

        return cls(
            entry_id=raw.get("entry_id", str(uuid.uuid4())),
            timestamp=timestamp,
            entry_type=entry_type,
            data=raw.get("data") or {},
            metadata=raw.get("metadata") or {},
        )


class BitacoraAuto:
    """
    Bitácora en modo JSONL (una entrada por línea).
    Es la "caja negra" de SYNAPSE.
    """

    def __init__(self, storage_path: str | Path = "data/bitacora/bitacora.jsonl") -> None:
        self._file_path = Path(storage_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: List[BitacoraEntry] = []
        self._load_entries()

    def log(
        self,
        entry_type: EntryType,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BitacoraEntry:
        entry = BitacoraEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            entry_type=entry_type,
            data=data,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._append_entry_to_file(entry)

        logger.info(
            "Bitácora entry logged",
            extra={
                "extra_data": {
                    "entry_id": entry.entry_id,
                    "entry_type": entry.entry_type.value,
                    "file_path": str(self._file_path),
                }
            },
        )

        return entry

    def get_entries(self) -> List[BitacoraEntry]:
        return list(self._entries)

    def _append_entry_to_file(self, entry: BitacoraEntry) -> None:
        try:
            with self._file_path.open("a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error writing bitácora entry",
                extra={
                    "extra_data": {
                        "error": str(exc),
                        "file_path": str(self._file_path),
                    }
                },
            )

    def _load_entries(self) -> None:
        """
        Carga histórico si existe. Fail-safe:
        - Si el archivo no existe → no hace nada
        - Si una línea está corrupta → se salta
        """
        if not self._file_path.exists():
            return

        try:
            with self._file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                        entry = BitacoraEntry.from_dict(raw)
                        self._entries.append(entry)
                    except json.JSONDecodeError:
                        logger.error(
                            "Invalid JSON in bitácora file, skipping line",
                            extra={"extra_data": {"line": line[:200]}},
                        )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error loading bitácora entries",
                extra={
                    "extra_data": {
                        "error": str(exc),
                        "file_path": str(self._file_path),
                    }
                },
            )


# Instancia global, igual que metrics_collector
bitacora = BitacoraAuto()
