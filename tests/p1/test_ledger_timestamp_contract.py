from __future__ import annotations

from synapse.infra.time_utc import (
    CLOCK_SOURCE_ID,
    MAX_CLOCK_SKEW_SECONDS,
    build_clock_stamp,
    parse_utc,
)


def test_clock_stamp_includes_required_fields():
    stamp = build_clock_stamp()

    assert stamp.clock_source_id == CLOCK_SOURCE_ID
    assert stamp.ingest_time.endswith("Z")
    assert stamp.event_time.endswith("Z")
    assert isinstance(stamp.clock_skew_estimate, float)
    assert stamp.clock_unreliable in (True, False)


def test_clock_stamp_marks_unreliable_above_threshold():
    stamp = build_clock_stamp(clock_skew_estimate=MAX_CLOCK_SKEW_SECONDS + 0.5)
    assert stamp.clock_unreliable is True


def test_parse_utc_roundtrip():
    stamp = build_clock_stamp()
    parsed = parse_utc(stamp.ingest_time)
    assert parsed.tzinfo is not None
