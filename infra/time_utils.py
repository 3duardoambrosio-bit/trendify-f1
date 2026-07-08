from __future__ import annotations

from datetime import datetime

from synapse.infra.time_utc import now_utc as authoritative_now_utc


def now_utc() -> datetime:
    """Compatibility alias for the canonical clock authority."""
    return authoritative_now_utc()
