from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, Optional

UTC: Final = timezone.utc
CLOCK_SOURCE_ID: Final = "synapse.time_utc.v1"
MAX_CLOCK_SKEW_SECONDS: Final = 30.0


@dataclass(frozen=True, slots=True)
class ClockStamp:
    ingest_time: str
    event_time: str
    clock_source_id: str
    clock_skew_estimate: float
    clock_unreliable: bool


def now_utc() -> datetime:
    return datetime.now(UTC)


def _require_tz_aware(dt: datetime, *, param_name: str = "dt") -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{param_name} must be tz-aware")
    return dt


def isoformat_z(dt: datetime, *, microsecond_precision: bool = True) -> str:
    aware = _require_tz_aware(dt).astimezone(UTC)
    timespec = "microseconds" if microsecond_precision else "seconds"
    return aware.isoformat(timespec=timespec).replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    canonical = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(canonical)
    if dt.tzinfo is None:
        raise ValueError(f"UTC timestamp must be tz-aware: {value}")
    return dt.astimezone(UTC)


def build_clock_stamp(
    *,
    now: Optional[datetime] = None,
    event_time: Optional[str] = None,
    clock_skew_estimate: float = 0.0,
    clock_unreliable: bool = False,
) -> ClockStamp:
    ingest_dt = (now or now_utc()).astimezone(UTC)
    ingest_text = isoformat_z(ingest_dt)

    event_text = event_time or ingest_text
    parsed_event = parse_utc(event_text)

    skew = abs((ingest_dt - parsed_event).total_seconds()) + abs(float(clock_skew_estimate))
    unreliable = bool(clock_unreliable or skew > MAX_CLOCK_SKEW_SECONDS)

    return ClockStamp(
        ingest_time=ingest_text,
        event_time=isoformat_z(parsed_event),
        clock_source_id=CLOCK_SOURCE_ID,
        clock_skew_estimate=round(skew, 6),
        clock_unreliable=unreliable,
    )