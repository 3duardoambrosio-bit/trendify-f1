from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _parse_ts_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("ts_utc debe ser str")

    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    dt = datetime.fromisoformat(s)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def test_ledger_events_have_ts_utc_parseable(tmp_path, monkeypatch):
    # Test hermético: NO depende de data/ real del repo
    repo = tmp_path
    ledger_dir = repo / "data" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    p = ledger_dir / "events.ndjson"

    lines = [
        {"ts_utc": "2025-01-01T00:00:00Z", "event": "toy"},
        {"ts_utc": "2025-01-01T00:00:01+00:00", "event": "toy"},
    ]

    with p.open("w", encoding="utf-8", newline="\n") as f:
        for obj in lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    monkeypatch.chdir(repo)

    p_rel = Path("data/ledger/events.ndjson")
    assert p_rel.exists()

    raw = p_rel.read_text(encoding="utf-8").splitlines()
    assert len(raw) >= 2

    for line in raw:
        if not line.strip():
            continue
        obj = json.loads(line)
        assert "ts_utc" in obj
        dt = _parse_ts_utc(obj["ts_utc"])
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timezone.utc.utcoffset(dt)
