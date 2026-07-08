from __future__ import annotations

import json

import synapse.ledger_ndjson as ledger


def test_build_event_includes_clock_authority_metadata():
    record = ledger.build_event(
        kind="test.event",
        payload={"value": 1},
    )

    assert record["kind"] == "test.event"
    assert record["ingest_time"].endswith("Z")
    assert record["event_time"].endswith("Z")
    assert record["clock_source_id"] == "synapse.time_utc.v1"
    assert "clock_skew_estimate" in record
    assert "clock_unreliable" in record


def test_append_event_is_append_only_with_monotonic_offsets(tmp_path):
    ledger_path = tmp_path / "runtime" / "ledger" / "events.ndjson"

    first = ledger.append_event(
        ledger.build_event(kind="test.first", payload={"value": 1}),
        path=ledger_path,
    )
    second = ledger.append_event(
        ledger.build_event(kind="test.second", payload={"value": 2}),
        path=ledger_path,
    )

    assert first["offset"] == 0
    assert second["offset"] == 1

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["offset"] == 0
    assert parsed[1]["offset"] == 1
    assert parsed[0]["payload"]["value"] == 1
    assert parsed[1]["payload"]["value"] == 2


def test_read_events_roundtrip(tmp_path):
    ledger_path = tmp_path / "runtime" / "ledger" / "events.ndjson"

    ledger.append_event(
        ledger.build_event(kind="test.a", payload={"value": "a"}),
        path=ledger_path,
    )
    ledger.append_event(
        ledger.build_event(kind="test.b", payload={"value": "b"}),
        path=ledger_path,
    )

    events = ledger.read_events(path=ledger_path)

    assert len(events) == 2
    assert events[0]["offset"] == 0
    assert events[1]["offset"] == 1
    assert events[0]["kind"] == "test.a"
    assert events[1]["kind"] == "test.b"
