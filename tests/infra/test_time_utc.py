from __future__ import annotations

import pytest
from datetime import datetime, timezone

from synapse.infra.time_utc import now_utc, isoformat_z


def test_now_utc_is_tz_aware_and_utc():
    dt = now_utc()
    assert dt.tzinfo == timezone.utc


def test_isoformat_z_emits_trailing_z_and_no_offset():
    dt = datetime(2020, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
    s = isoformat_z(dt, microsecond_precision=True)
    assert s.endswith("Z")
    assert "+00:00" not in s
    assert "2020-01-02T03:04:05" in s


def test_isoformat_z_strips_microseconds_when_requested():
    dt = datetime(2020, 1, 2, 3, 4, 5, 999999, tzinfo=timezone.utc)
    s = isoformat_z(dt, microsecond_precision=False)
    assert s.endswith("Z")
    assert ".999999" not in s
    assert s == "2020-01-02T03:04:05Z"


def test_isoformat_z_rejects_naive_datetime():
    dt = datetime(2020, 1, 2, 3, 4, 5)
    with pytest.raises(ValueError):
        isoformat_z(dt)
