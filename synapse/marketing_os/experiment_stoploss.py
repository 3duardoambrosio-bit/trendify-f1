from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StopLossPolicy:
    roas_min: float
    max_spend_mxn: float
    min_events: int


def default_policy_mx() -> StopLossPolicy:
    # Conservative default: stop bleeding early.
    return StopLossPolicy(roas_min=1.2, max_spend_mxn=800.0, min_events=3)


def evaluate_stop_loss(
    *,
    spend_mxn: float,
    revenue_mxn: float,
    events: int,
    policy: StopLossPolicy,
) -> dict[str, object]:
    roas = (revenue_mxn / spend_mxn) if spend_mxn > 0 else 0.0
    breached_spend = spend_mxn >= policy.max_spend_mxn
    breached_roas = roas < policy.roas_min

    should_stop = (events >= policy.min_events) and breached_spend and breached_roas
    return {
        "roas": roas,
        "breached_spend": breached_spend,
        "breached_roas": breached_roas,
        "should_stop": should_stop,
        "policy": {
            "roas_min": policy.roas_min,
            "max_spend_mxn": policy.max_spend_mxn,
            "min_events": policy.min_events,
        },
    }
