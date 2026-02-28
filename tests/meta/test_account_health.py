from __future__ import annotations

from decimal import Decimal

from synapse.meta.account_health import (
    AccountHealthChecker,
    AccountHealthConfig,
    AccountMetrics,
)


def test_healthy_account_can_publish() -> None:
    cfg = AccountHealthConfig(
        disapproval_yellow=Decimal("0.10"),
        disapproval_red=Decimal("0.20"),
        velocity_yellow=Decimal("3.0"),
        warm_up_age_days=10,
    )
    c = AccountHealthChecker(cfg)
    m = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=1.0, account_age_days=30, has_policy_violation=False)
    s = c.check(m)
    assert s.risk_level == "green"
    assert s.can_publish is True
    assert s.can_scale is True


def test_high_disapproval_blocks_publish() -> None:
    c = AccountHealthChecker(AccountHealthConfig())
    m = AccountMetrics(ad_disapproval_rate=0.25, spend_velocity_ratio=1.0, account_age_days=30, has_policy_violation=False)
    s = c.check(m)
    assert s.risk_level == "red"
    assert s.can_publish is False


def test_velocity_spike_blocks_scale() -> None:
    c = AccountHealthChecker(AccountHealthConfig())
    m = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=4.0, account_age_days=30, has_policy_violation=False)
    s = c.check(m)
    assert s.risk_level == "yellow"
    assert s.can_scale is False


def test_policy_violation_blocks_everything() -> None:
    c = AccountHealthChecker(AccountHealthConfig())
    m = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=1.0, account_age_days=30, has_policy_violation=True)
    s = c.check(m)
    assert s.risk_level == "red"
    assert s.can_publish is False
    assert s.can_scale is False