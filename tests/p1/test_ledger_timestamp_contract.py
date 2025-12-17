from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _is_iso8601(ts: str) -> bool:
    try:
        # soporta "Z" y "+00:00"
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def test_ledger_events_have_ts_utc_parseable():
    p = Path("data/ledger/events.ndjson")
    assert p.exists()

    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) > 0

    # Contrato del WRITER actual: valida eventos recientes (no basura histórica vieja)
    sample = lines[-10:] if len(lines) >= 10 else lines

    for ln in sample:
        ev = json.loads(ln)
        ts = (ev.get("ts_utc") or "").strip()
        assert ts, f"missing/blank ts_utc: keys={sorted(ev.keys())}"
        assert _is_iso8601(ts), f"ts_utc not ISO8601: {ts}"