from __future__ import annotations

from decimal import Decimal

import pytest

from infra.ledger_v2 import (
    AMENDMENT_DOCUMENT_TYPE,
    APPEND_ONLY_DOCUMENT_TYPE,
    build_ledger_record,
    canonicalize_money,
    compute_checksum,
    rebuild_checksums,
    wrap_as_amendment,
    wrap_as_append_only,
)


def test_compute_checksum_is_deterministic():
    payload = {"b": 2, "a": 1}
    assert compute_checksum(payload) == compute_checksum({"a": 1, "b": 2})


def test_canonicalize_money_rounds_half_up():
    assert canonicalize_money("10") == Decimal("10.00")
    assert canonicalize_money("10.125") == Decimal("10.13")


def test_build_append_only_record_has_expected_shape():
    record = build_ledger_record(
        event_id="evt-1",
        document_type=APPEND_ONLY_DOCUMENT_TYPE,
        payload={"value": 1},
    )

    data = record.to_dict()
    assert data["event_id"] == "evt-1"
    assert data["document_type"] == APPEND_ONLY_DOCUMENT_TYPE
    assert data["payload"]["value"] == 1
    assert data["payload_checksum"]
    assert data["ingest_time"].endswith("Z")
    assert data["event_time"].endswith("Z")


def test_wrap_as_amendment_requires_base_event_id():
    record = build_ledger_record(
        event_id="evt-2",
        document_type=AMENDMENT_DOCUMENT_TYPE,
        payload={"value": 2},
    )

    with pytest.raises(ValueError):
        wrap_as_amendment(
            record,
            clock_source_id="clock.v1",
            clock_unreliable=False,
            clock_skew_estimate=0.0,
        )


def test_wrap_as_amendment_and_rebuild_checksums():
    record = build_ledger_record(
        event_id="evt-3",
        document_type=AMENDMENT_DOCUMENT_TYPE,
        payload={"value": 3},
        base_event_id="evt-1",
    )

    wrapped = wrap_as_amendment(
        record,
        clock_source_id="clock.v1",
        clock_unreliable=False,
        clock_skew_estimate=0.0,
    )

    wrapped_data = wrapped.to_dict()
    assert wrapped_data["status"] == "AMENDED"
    assert wrapped_data["base_event_id"] == "evt-1"

    rebuilt = rebuild_checksums(
        [
            {"payload": {"value": 1}, "payload_checksum": "bad"},
            {"payload": {"value": 2}, "payload_checksum": "bad"},
        ]
    )
    assert rebuilt[0]["payload_checksum"] != "bad"
    assert rebuilt[1]["payload_checksum"] != "bad"


def test_wrap_as_append_only():
    record = build_ledger_record(
        event_id="evt-4",
        document_type=APPEND_ONLY_DOCUMENT_TYPE,
        payload={"value": 4},
    )

    wrapped = wrap_as_append_only(
        record,
        clock_source_id="clock.v1",
        clock_unreliable=False,
        clock_skew_estimate=0.0,
    )

    data = wrapped.to_dict()
    assert data["status"] == "APPENDED"
    assert data["clock_source_id"] == "clock.v1"
