# synapse/reporting/audit_viewer.py
"""
Audit Trail Viewer (Ledger -> Markdown).

Objetivo:
- Sacar "qué pasó con X producto" sin abrir NDJSON a mano.
- Reporte markdown con timeline y tabla.

Compat:
- Si existe synapse.infra.ledger.Ledger con query(), lo usamos.
- Si no, parseamos NDJSON directo.

Esto es F1 para operar y auditar rápido.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class AuditQuery:
    entity_id: str = ""
    wave_id: str = ""
    limit: int = 200


def _read_ndjson_files(ledger_dir: str) -> Iterable[Dict[str, Any]]:
    if not os.path.exists(ledger_dir):
        return []
    files = []
    for name in os.listdir(ledger_dir):
        if name.lower().endswith(".ndjson"):
            files.append(os.path.join(ledger_dir, name))
    files.sort()
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def _match(ev: Dict[str, Any], q: AuditQuery) -> bool:
    if q.entity_id and str(ev.get("entity_id", "")) != str(q.entity_id):
        return False
    if q.wave_id and str(ev.get("wave_id", "")) != str(q.wave_id):
        return False
    return True


def query_events(ledger_dir: str, q: AuditQuery) -> List[Dict[str, Any]]:
    # Try Ledger API first
    try:
        from synapse.infra.ledger import Ledger  # type: ignore
        led = Ledger(ledger_dir)
        # Prefer query signature if present
        if hasattr(led, "query"):
            kwargs = {}
            if q.entity_id:
                kwargs["entity_id"] = q.entity_id
            if q.wave_id:
                kwargs["wave_id"] = q.wave_id
            events = led.query(**kwargs)  # type: ignore
            # Normalize dataclasses -> dict
            out = []
            for ev in events[: q.limit]:
                if hasattr(ev, "to_dict"):
                    out.append(ev.to_dict())  # type: ignore
                elif hasattr(ev, "__dict__"):
                    out.append(dict(ev.__dict__))  # type: ignore
                else:
                    out.append(ev)  # already dict?
            return out[: q.limit]
    except Exception:
        pass

    out2 = []
    for ev in _read_ndjson_files(ledger_dir):
        if _match(ev, q):
            out2.append(ev)
            if len(out2) >= q.limit:
                break
    return out2


def render_markdown(events: List[Dict[str, Any]], title: str = "Audit Report") -> str:
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"Total events: **{len(events)}**")
    lines.append("")
    lines.append("| ts | event_type | entity | wave_id | note |")
    lines.append("|---|---|---|---|---|")

    for ev in events:
        ts = str(ev.get("timestamp") or ev.get("ts") or "")
        et = str(ev.get("event_type") or "")
        entity = f'{ev.get("entity_type","")}:{ev.get("entity_id","")}'
        wave = str(ev.get("wave_id") or "")
        payload = ev.get("payload") or {}
        note = ""
        if isinstance(payload, dict):
            note = str(payload.get("status") or payload.get("reason") or payload.get("message") or "")[:80]
        lines.append(f"| {ts} | {et} | {entity} | {wave} | {note} |")

    lines.append("")
    return "\n".join(lines)


def write_report(md: str, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    return out_path


def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-dir", default="data/ledger")
    parser.add_argument("--entity-id", default="")
    parser.add_argument("--wave-id", default="")
    parser.add_argument("--out", default="data/audit/audit_report_latest.md")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    q = AuditQuery(entity_id=args.entity_id, wave_id=args.wave_id, limit=args.limit)
    evs = query_events(args.ledger_dir, q)
    md = render_markdown(evs, title="SYNAPSE Audit Trail")
    write_report(md, args.out)
    print(json.dumps({"events": len(evs), "out": os.path.abspath(args.out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
