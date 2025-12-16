import json
from infra.ledger_ndjson import LedgerNDJSON


def test_ledger_writes_valid_ndjson(tmp_path):
    p = tmp_path / "events.ndjson"
    ledger = LedgerNDJSON(p)

    ev = ledger.write(
        event_type="DECISION_MADE",
        entity_type="product",
        entity_id="r004",
        payload={"decision": "LAUNCH_CANDIDATE", "score": 79.84},
        trace_id="trace123",
        ts="2025-12-16T12:00:00+00:00",
    )

    assert ev.entity_id == "r004"

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    obj = json.loads(lines[0])
    assert obj["event_type"] == "DECISION_MADE"
    assert obj["entity_type"] == "product"
    assert obj["entity_id"] == "r004"
    assert obj["trace_id"] == "trace123"
    assert obj["payload"]["decision"] == "LAUNCH_CANDIDATE"