import json

from synapse.ledger_ndjson import append_event, build_event, cmd_validate, main, read_events


def test_ledger_writes_valid_ndjson(tmp_path):
    p = tmp_path / "events.ndjson"

    ev = append_event(
        build_event(
            kind="DECISION_MADE",
            payload={
                "entity_type": "product",
                "entity_id": "r004",
                "trace_id": "trace123",
                "decision": "LAUNCH_CANDIDATE",
                "score": 79.84,
            },
            event_time="2025-12-16T12:00:00+00:00",
        ),
        path=p,
    )

    assert ev["offset"] == 0

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    obj = json.loads(lines[0])
    assert obj["kind"] == "DECISION_MADE"
    assert obj["payload"]["entity_type"] == "product"
    assert obj["payload"]["entity_id"] == "r004"
    assert obj["payload"]["trace_id"] == "trace123"
    assert obj["payload"]["decision"] == "LAUNCH_CANDIDATE"

    rows = read_events(p)
    assert len(rows) == 1
    assert rows[0]["kind"] == "DECISION_MADE"

def test_validate_cli_clean_ledger_returns_zero(tmp_path):
    p = tmp_path / "events.ndjson"
    append_event(
        build_event(kind="DECISION_MADE", payload={"entity_id": "r004"}),
        path=p,
    )

    assert cmd_validate(p) == 0
    assert main(["--path", str(p), "validate"]) == 0


def test_validate_cli_missing_ledger_is_clean_and_readonly(tmp_path):
    p = tmp_path / "missing.ndjson"

    assert cmd_validate(p) == 0
    # Validation is read-only: it must never create or repair the ledger.
    assert not p.exists()


def test_validate_cli_detects_corrupt_lines(tmp_path):
    p = tmp_path / "events.ndjson"
    append_event(
        build_event(kind="DECISION_MADE", payload={"entity_id": "r004"}),
        path=p,
    )
    with p.open("a", encoding="utf-8") as handle:
        handle.write("{not valid json\n")
        handle.write(json.dumps({"kind": "X"}) + "\n")  # missing payload dict

    rc = main(["--path", str(p), "validate"])
    assert rc == 2
