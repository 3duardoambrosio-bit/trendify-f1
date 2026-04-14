from __future__ import annotations

import json
from pathlib import Path

from synapse.ledger_ndjson import append_event, build_event, read_events


def _append(path: Path, *, kind: str, payload: dict) -> dict:
    record = build_event(kind=kind, payload=payload)
    return append_event(record, path=path)


def test_ledger_append_and_read(tmp_path: Path) -> None:
    p = tmp_path / "events.ndjson"

    _append(
        p,
        kind="DECISION_MADE",
        payload={
            "entity_type": "product",
            "entity_id": "r004",
            "decision": "LAUNCH_CANDIDATE",
        },
    )
    _append(
        p,
        kind="SPEND_APPROVED",
        payload={
            "entity_type": "product",
            "entity_id": "r004",
            "amount": 5,
        },
    )

    rows = read_events(p)
    assert len(rows) == 2
    assert rows[0]["kind"] == "DECISION_MADE"
    assert rows[1]["payload"]["amount"] == 5

    raw = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(raw) == 2
    json.loads(raw[0])
    json.loads(raw[1])


def test_ledger_schema_required_fields(tmp_path: Path) -> None:
    p = tmp_path / "events.ndjson"
    ev = append_event(
        build_event(
            kind="PING",
            payload={
                "entity_type": "system",
                "entity_id": "synapse",
                "ok": True,
            },
        ),
        path=p,
    )

    for k in [
        "event_id",
        "kind",
        "payload",
        "ingest_time",
        "event_time",
        "clock_source_id",
        "clock_skew_estimate",
        "clock_unreliable",
        "policy_version",
        "payload_schema_version",
        "offset",
    ]:
        assert k in ev