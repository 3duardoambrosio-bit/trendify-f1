# synapse/infra/ledger.py
"""
Ledger - Event logging durable para SYNAPSE.

Características:
- Append-only NDJSON
- Rotación mensual automática
- Checksum por evento
- Query por entity_id, event_type, wave_id

Uso:
    ledger = Ledger()
    ledger.write("PRODUCT_EVALUATED", "product", "34357", {"score": 0.75})
    
    events = ledger.query(entity_id="34357")
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading


# ============================================================
# TYPES
# ============================================================

@dataclass
class LedgerEvent:
    """Evento del ledger."""
    timestamp: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: Dict[str, Any]
    wave_id: str = ""
    checksum: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LedgerEvent":
        return cls(**d)


# ============================================================
# LEDGER
# ============================================================

class Ledger:
    """
    Ledger durable con append-only y rotación.
    
    Archivos:
        data/ledger/ledger_YYYY_MM.ndjson
    """
    
    def __init__(self, base_dir: str = "data/ledger"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
    def _get_current_file(self) -> Path:
        """Retorna archivo del mes actual."""
        now = datetime.now(timezone.utc)
        filename = f"ledger_{now.year}_{now.month:02d}.ndjson"
        return self.base_dir / filename
    
    def _compute_checksum(self, event: LedgerEvent) -> str:
        """Computa checksum SHA256 del evento (sin checksum field)."""
        d = event.to_dict()
        d.pop("checksum", None)
        serialized = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]
    
    def write(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        wave_id: str = "",
    ) -> LedgerEvent:
        """
        Escribe evento al ledger.
        
        Args:
            event_type: Tipo de evento (ej. PRODUCT_EVALUATED)
            entity_type: Tipo de entidad (ej. product, campaign)
            entity_id: ID de la entidad
            payload: Datos del evento
            wave_id: ID de la wave que generó el evento
            
        Returns:
            LedgerEvent creado
        """
        event = LedgerEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            wave_id=wave_id,
        )
        
        event.checksum = self._compute_checksum(event)
        
        with self._lock:
            file_path = self._get_current_file()
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        
        return event
    
    def query(
        self,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        event_type: Optional[str] = None,
        wave_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[LedgerEvent]:
        """
        Query eventos del ledger.
        
        Args:
            entity_id: Filtrar por entity_id
            entity_type: Filtrar por entity_type
            event_type: Filtrar por event_type
            wave_id: Filtrar por wave_id
            limit: Máximo de resultados
            
        Returns:
            Lista de eventos (más recientes primero)
        """
        events = []
        
        # Read all ledger files (sorted by name = by date)
        ledger_files = sorted(self.base_dir.glob("ledger_*.ndjson"), reverse=True)
        
        for file_path in ledger_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        
                        try:
                            d = json.loads(line)
                            event = LedgerEvent.from_dict(d)
                            
                            # Apply filters
                            if entity_id and event.entity_id != entity_id:
                                continue
                            if entity_type and event.entity_type != entity_type:
                                continue
                            if event_type and event.event_type != event_type:
                                continue
                            if wave_id and event.wave_id != wave_id:
                                continue
                            
                            events.append(event)
                            
                            if len(events) >= limit:
                                break
                        except (json.JSONDecodeError, TypeError):
                            continue
                
                if len(events) >= limit:
                    break
            except (json.JSONDecodeError, TypeError):
                continue
        
        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)
        
        return events[:limit]
    
    def get_last_event(
        self,
        entity_id: str,
        event_type: Optional[str] = None,
    ) -> Optional[LedgerEvent]:
        """Obtiene último evento de una entidad."""
        events = self.query(entity_id=entity_id, event_type=event_type, limit=1)
        return events[0] if events else None
    
    def verify_integrity(self) -> List[str]:
        """
        Verifica integridad de eventos (checksums).
        
        Returns:
            Lista de errores encontrados
        """
        errors = []
        
        for file_path in self.base_dir.glob("ledger_*.ndjson"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if not line.strip():
                            continue
                        
                        try:
                            d = json.loads(line)
                            event = LedgerEvent.from_dict(d)
                            
                            expected_checksum = self._compute_checksum(event)
                            if event.checksum != expected_checksum:
                                errors.append(
                                    f"{file_path.name}:{i} - Checksum mismatch "
                                    f"(expected {expected_checksum}, got {event.checksum})"
                                )
                        except json.JSONDecodeError:
                            errors.append(f"{file_path.name}:{i} - Invalid JSON")
            except Exception as e:
                errors.append(f"{file_path.name} - Read error: {e}")
        
        return errors
    
    def count_events(self, event_type: Optional[str] = None) -> int:
        """Cuenta eventos (opcionalmente por tipo)."""
        count = 0
        
        for file_path in self.base_dir.glob("ledger_*.ndjson"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        
                        if event_type:
                            try:
                                d = json.loads(line)
                                if d.get("event_type") == event_type:
                                    count += 1
                            except Exception:
                                pass
                        else:
                            count += 1
            except Exception:
                pass
        
        return count


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

_default_ledger: Optional[Ledger] = None


def get_ledger() -> Ledger:
    """Obtiene instancia singleton del ledger."""
    global _default_ledger
    if _default_ledger is None:
        _default_ledger = Ledger()
    return _default_ledger


def log_event(
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: Dict[str, Any],
    wave_id: str = "",
) -> LedgerEvent:
    """Shortcut para escribir evento."""
    return get_ledger().write(event_type, entity_type, entity_id, payload, wave_id)
