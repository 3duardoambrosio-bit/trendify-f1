from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

UTC: Final = timezone.utc


def now_utc() -> datetime:
    """Return a timezone-aware UTC datetime.

    Returns:
        datetime: tz-aware datetime with tzinfo=UTC.
    """
    return datetime.now(UTC)


def isoformat_z(dt: datetime, *, microsecond_precision: bool = True) -> str:
    """Convert tz-aware datetime to ISO-8601 string with trailing 'Z'.

    Naive datetimes are rejected to prevent silent timezone bugs.

    Args:
        dt: timezone-aware datetime.
        microsecond_precision: if False, strip microseconds.

    Returns:
        ISO-8601 string ending in 'Z'.

    Raises:
        ValueError: if dt is naive (tzinfo is None).
    """
    if dt.tzinfo is None:
        raise ValueError("isoformat_z requires a timezone-aware datetime (tzinfo != None)")

    dt_utc = dt.astimezone(UTC)
    if not microsecond_precision:
        dt_utc = dt_utc.replace(microsecond=0)

    s = dt_utc.isoformat()
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s
