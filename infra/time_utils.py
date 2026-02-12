from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)
