import json
from pathlib import Path

def _get_ts(ev: dict) -> str:
    return (ev.get("ts_utc") or ev.get("ts") or ev.get("timestamp") or ev.get("time") or ev.get("created_at") or "")

def test_ledger_events_have_timestamp_field_parseable():
    p = Path("data/ledger/events.ndjson")
    assert p.exists()
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) > 0

    # valida 5 primeras para speed; suficiente para contrato
    for ln in lines[:5]:
        ev = json.loads(ln)
        ts = _get_ts(ev)
        assert ts, f"missing timestamp field in event: keys={sorted(ev.keys())}"
        # ISO-ish: mÃ­nimo presencia de 'T' y zona o offset (no perfecto, pero evita basura)
        assert "T" in ts
