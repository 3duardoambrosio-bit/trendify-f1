from __future__ import annotations

import json
from pathlib import Path

from core.ledger import Ledger


def test_ledger_append_and_read(tmp_path: Path) -> None:
    p = tmp_path / "events.ndjson"
    ledger = Ledger(path=str(p))

    ledger.append("DECISION_MADE", "product", "r004", {"decision": "LAUNCH_CANDIDATE"})
    ledger.append("SPEND_APPROVED", "product", "r004", {"amount": 5})

    rows = list(ledger.iter_events())
    assert len(rows) == 2
    assert rows[0]["event_type"] == "DECISION_MADE"
    assert rows[1]["payload"]["amount"] == 5

    # Each line is valid JSON
    raw = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(raw) == 2
    json.loads(raw[0])
    json.loads(raw[1])


def test_ledger_schema_required_fields(tmp_path: Path) -> None:
    p = tmp_path / "events.ndjson"
    ledger = Ledger(path=str(p))
    ev = ledger.append("PING", "system", "synapse", {"ok": True})
    d = ev.to_dict()

    for k in ["event_id", "ts_utc", "event_type", "entity_type", "entity_id", "payload"]:
        assert k in d