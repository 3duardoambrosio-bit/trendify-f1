from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from synapse.meta.warm_up_protocol import WarmUpConfig, WarmUpProtocol


def test_warm_up_day1_returns_initial_limit() -> None:
    cfg = WarmUpConfig(initial_daily_usd=Decimal("5"), ramp_pct=Decimal("0.20"), min_account_age_days=10, ramp_start_day=3)
    created = datetime.now(timezone.utc) - timedelta(days=1)
    w = WarmUpProtocol(cfg, created)
    assert w.get_daily_limit(1) == Decimal("5.00")


def test_warm_up_ramp_day5() -> None:
    cfg = WarmUpConfig(initial_daily_usd=Decimal("5"), ramp_pct=Decimal("0.20"), min_account_age_days=10, ramp_start_day=3)
    created = datetime.now(timezone.utc) - timedelta(days=1)
    w = WarmUpProtocol(cfg, created)
    # day 5 => initial*(1.2)^(5-3)=5*1.44=7.20
    assert w.get_daily_limit(5) == Decimal("7.20")


def test_warm_up_never_exceeds_cap() -> None:
    cfg = WarmUpConfig(initial_daily_usd=Decimal("5"), ramp_pct=Decimal("0.20"), min_account_age_days=10, ramp_start_day=3)
    created = datetime.now(timezone.utc) - timedelta(days=1)
    w = WarmUpProtocol(cfg, created)
    cap = Decimal("10.00")
    for d in range(1, 50):
        assert w.get_daily_limit(d, daily_cap=cap) <= cap


def test_warm_up_blocks_future_date() -> None:
    cfg = WarmUpConfig()
    future = datetime.now(timezone.utc) + timedelta(days=2)
    w = WarmUpProtocol(cfg, future)
    assert w.get_daily_limit(1) == Decimal("0")


@given(day=st.integers(min_value=1, max_value=120))
def test_warm_up_property_non_negative_and_capped(day: int) -> None:
    cfg = WarmUpConfig()
    created = datetime.now(timezone.utc) - timedelta(days=1)
    w = WarmUpProtocol(cfg, created)
    cap = Decimal("10.00")
    out = w.get_daily_limit(day, daily_cap=cap)
    assert out >= Decimal("0")
    assert out <= cap