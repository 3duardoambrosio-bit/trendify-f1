from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

__MARKER__ = "LEDGER_TAIL_2026-01-13_V1"
LEDGER_REL = Path("data/ledger/events.ndjson")


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _read_lines(p: Path) -> List[str]:
    if not p.exists():
        return []
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.ledger_tail", description="Print last N ledger events (safe, no python -c).")
    ap.add_argument("--n", type=int, default=10, help="How many last events to show.")
    ap.add_argument("--pretty", action="store_true", help="Pretty JSON output per event.")
    ap.add_argument("--fields", default="", help="Comma-separated fields, e.g. ts_utc,payload.event_type,payload.utm_content")
    args = ap.parse_args(argv)

    repo = Path.cwd()
    p = repo / LEDGER_REL
    lines = _read_lines(p)

    if not lines:
        cli_print(json.dumps({"marker": __MARKER__, "status": "EMPTY", "ledger": str(p)}, ensure_ascii=False, indent=2))
        return 0

    sample = lines[-args.n:] if len(lines) > args.n else lines
    fields = [f.strip() for f in (args.fields or "").split(",") if f.strip()]

    if fields:
        out_rows: List[Dict[str, Any]] = []
        for ln in sample:
            try:
                ev = json.loads(ln)
            except (json.JSONDecodeError, TypeError):
                out_rows.append({"_error": "bad_json"})
                continue
            row: Dict[str, Any] = {}
            for f in fields:
                row[f] = _get_path(ev, f)
            out_rows.append(row)
        cli_print(json.dumps(
            {
                "marker": __MARKER__,
                "status": "OK",
                "count": len(lines),
                "showing": len(sample),
                "fields": fields,
                "rows": out_rows,
            },
            ensure_ascii=False,
            indent=2,
            default=str
        ))
        return 0

    # default: print events
    for ln in sample:
        if args.pretty:
            try:
                ev = json.loads(ln)
                cli_print(json.dumps(ev, ensure_ascii=False, indent=2, default=str))
            except Exception:
                cli_print(ln)
        else:
            cli_print(ln)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
