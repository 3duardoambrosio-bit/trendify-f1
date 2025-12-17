from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
import json

@dataclass(frozen=True)
class LedgerStats:
    total: int
    by_event: Dict[str, int]
    by_entity: Dict[str, int]

def _inc(d: Dict[str,int], k: str) -> None:
    d[k] = d.get(k, 0) + 1

def analyze_ndjson(lines: List[str]) -> LedgerStats:
    by_event: Dict[str,int] = {}
    by_entity: Dict[str,int] = {}
    total = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            _inc(by_event, "_INVALID_JSON")
            total += 1
            continue

        ev = str(obj.get("event_type", "UNKNOWN"))
        ent = str(obj.get("entity_type", "UNKNOWN"))
        _inc(by_event, ev)
        _inc(by_entity, ent)
        total += 1

    return LedgerStats(total=total, by_event=by_event, by_entity=by_entity)