# synapse/reporting/audit_viewer.py
"""
Audit Trail Viewer (Ledger -> Markdown).

Objetivo:
- Sacar "qué pasó con X producto" sin abrir NDJSON a mano.
- Reporte markdown con timeline y tabla.

High-integrity:
- Usa el ledger canónico synapse.ledger_ndjson.
- NO depende de synapse.infra.ledger.
- Soporta leer un archivo .ndjson único o un directorio con múltiples .ndjson.
"""

from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from synapse.ledger_ndjson import read_events

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditQuery:
    entity_id: str = ""
    wave_id: str = ""
    limit: int = 200


def _candidate_ndjson_paths(ledger_dir: str) -> List[Path]:
    base = Path(ledger_dir)

    if not base.exists():
        return []

    if base.is_file():
        return [base] if base.suffix.lower() == ".ndjson" else []

    paths = sorted(
        [p for p in base.iterdir() if p.is_file() and p.suffix.lower() == ".ndjson"],
        key=lambda p: p.name,
    )
    return paths


def _read_ndjson_files(ledger_dir: str) -> Iterable[Dict[str, Any]]:
    for path in _candidate_ndjson_paths(ledger_dir):
        try:
            for ev in read_events(path):
                if isinstance(ev, dict):
                    yield ev
        except Exception:
            logger.debug("suppressed exception while reading canonical ledger", exc_info=True)


def _match(ev: Dict[str, Any], q: AuditQuery) -> bool:
    if q.entity_id and str(ev.get("entity_id", "")) != str(q.entity_id):
        return False
    if q.wave_id and str(ev.get("wave_id", "")) != str(q.wave_id):
        return False
    return True


def query_events(ledger_dir: str, q: AuditQuery) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in _read_ndjson_files(ledger_dir):
        if _match(ev, q):
            out.append(ev)
            if len(out) >= q.limit:
                break
    return out


def render_markdown(events: List[Dict[str, Any]], title: str = "Audit Report") -> str:
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"Total events: **{len(events)}**")
    lines.append("")
    lines.append("| ts | event_type | entity | wave_id | note |")
    lines.append("|---|---|---|---|---|")

    for ev in events:
        ts = str(
            ev.get("timestamp")
            or ev.get("ts")
            or ev.get("event_time")
            or ev.get("ingest_time")
            or ""
        )
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
    cli_print(json.dumps({"events": len(evs), "out": os.path.abspath(args.out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())